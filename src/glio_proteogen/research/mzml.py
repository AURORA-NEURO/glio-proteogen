"""Bounded mzML spectrum extraction for research workflows."""

from __future__ import annotations

import base64
import gzip
import io
import math
import struct
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO, cast

from defusedxml import ElementTree

if TYPE_CHECKING:
    from xml.etree.ElementTree import Element


@dataclass(frozen=True, slots=True)
class Spectrum:
    spectrum_id: str
    ms_level: int
    retention_time_seconds: float | None
    mz: tuple[float, ...]
    intensity: tuple[float, ...]
    precursor_mz: float | None = None
    precursor_charge: int | None = None


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _bounded_zlib(data: bytes, max_output_bytes: int) -> bytes:
    decoder = zlib.decompressobj()
    output = decoder.decompress(data, max_output_bytes + 1)
    if len(output) > max_output_bytes or decoder.unconsumed_tail:
        raise ValueError("mzML compressed array exceeds the research limit")
    output += decoder.flush(max_output_bytes - len(output) + 1)
    if len(output) > max_output_bytes or not decoder.eof:
        raise ValueError("mzML compressed array exceeds the research limit")
    return output


def _binary_array(element: Element, *, max_output_bytes: int) -> tuple[float, ...]:
    encoded = element.find("{*}binary")
    if encoded is None or not encoded.text:
        return ()
    data = base64.b64decode(encoded.text, validate=True)
    compression = {item.attrib.get("accession") for item in element.findall("{*}cvParam")}
    if "MS:1000574" in compression:
        data = _bounded_zlib(data, max_output_bytes)
    if "MS:1000523" in compression:
        width, fmt = 4, "f"
    elif "MS:1000521" in compression:
        width, fmt = 8, "d"
    else:
        raise ValueError("mzML binary array has no supported precision")
    if len(data) % width:
        raise ValueError("mzML binary array has a partial value")
    return tuple(struct.unpack(f"<{len(data) // width}{fmt}", data))


def _read_bounded_gzip(source: BinaryIO, max_bytes: int) -> bytes:
    output = bytearray()
    with gzip.GzipFile(fileobj=source) as decoded:
        while len(output) <= max_bytes:
            chunk = decoded.read(min(1024 * 1024, max_bytes + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
    if len(output) > max_bytes:
        raise ValueError("decoded mzML payload exceeds the research limit")
    return bytes(output)


class _PrefixedReader(io.RawIOBase):
    def __init__(self, prefix: bytes, source: BinaryIO) -> None:
        super().__init__()
        self._prefix = io.BytesIO(prefix)
        self._source = source

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        prefix = self._prefix.read(size)
        if size < 0:
            return prefix + self._source.read()
        if len(prefix) == size:
            return prefix
        return prefix + self._source.read(size - len(prefix))


def _payload(source: bytes | bytearray | BinaryIO, max_bytes: int) -> bytes:
    stream: BinaryIO = (
        io.BytesIO(bytes(source)) if isinstance(source, (bytes, bytearray)) else source
    )
    header = stream.read(2)
    if header == b"\x1f\x8b":
        if stream.seekable():
            stream.seek(0)
            return _read_bounded_gzip(stream, max_bytes)
        return _read_bounded_gzip(cast("BinaryIO", _PrefixedReader(header, stream)), max_bytes)
    payload = header + stream.read(max_bytes + 1 - len(header))
    if len(payload) > max_bytes:
        raise ValueError("mzML payload exceeds the research limit")
    return payload


def parse_mzml(
    source: bytes | bytearray | BinaryIO,
    *,
    max_bytes: int = 256 * 1024 * 1024,
    max_spectra: int = 100_000,
) -> tuple[Spectrum, ...]:
    """Decode bounded m/z and intensity arrays from one mzML document."""
    if not 0 < max_bytes <= 512 * 1024 * 1024 or not 0 < max_spectra <= 1_000_000:
        raise ValueError("research limits are outside supported bounds")
    root = ElementTree.fromstring(_payload(source, max_bytes))
    output: list[Spectrum] = []
    for element in root.iter():
        if _local(element.tag) != "spectrum":
            continue
        if len(output) >= max_spectra:
            raise ValueError("mzML spectrum count exceeds the research limit")
        ms_level = 1
        retention: float | None = None
        precursor_mz: float | None = None
        precursor_charge: int | None = None
        for cv in element.findall("{*}cvParam"):
            accession = cv.attrib.get("accession")
            if accession == "MS:1000511":
                ms_level = int(cv.attrib["value"])
            elif accession == "MS:1000016":
                value = float(cv.attrib["value"])
                retention = value * 60.0 if cv.attrib.get("unitName") == "minute" else value
        for cv in element.findall(".//{*}cvParam"):
            accession = cv.attrib.get("accession")
            if accession == "MS:1000744" and cv.attrib.get("value") is not None:
                precursor_mz = float(cv.attrib["value"])
            elif accession == "MS:1000041" and cv.attrib.get("value") is not None:
                precursor_charge = int(cv.attrib["value"])
        if precursor_mz is not None and (not math.isfinite(precursor_mz) or precursor_mz <= 0):
            raise ValueError("mzML precursor m/z must be finite and positive")
        if precursor_charge is not None and precursor_charge < 1:
            raise ValueError("mzML precursor charge must be positive")
        arrays = element.findall(".//{*}binaryDataArray")
        mz: tuple[float, ...] = ()
        intensity: tuple[float, ...] = ()
        for array in arrays:
            accessions = {item.attrib.get("accession") for item in array.findall("{*}cvParam")}
            values = _binary_array(array, max_output_bytes=max_bytes)
            if "MS:1000514" in accessions:
                mz = values
            elif "MS:1000515" in accessions:
                intensity = values
        if len(mz) != len(intensity):
            raise ValueError("mzML m/z and intensity arrays differ in length")
        output.append(
            Spectrum(
                element.attrib.get("id", f"scan={len(output) + 1}"),
                ms_level,
                retention,
                mz,
                intensity,
                precursor_mz,
                precursor_charge,
            )
        )
    return tuple(output)
