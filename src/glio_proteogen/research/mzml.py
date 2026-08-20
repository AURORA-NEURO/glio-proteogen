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
    precursor_ambiguous: bool = False


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
    # ``BinaryIO.read(n)`` may legally return fewer than n bytes before EOF.
    # Drain the sniffed prefix before deciding whether the stream is gzip so a
    # throttled or non-seekable source cannot be mistaken for a short payload.
    prefix = bytearray()
    while len(prefix) < 2:
        chunk = stream.read(2 - len(prefix))
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("mzML binary stream must return bytes")
        if not chunk:
            break
        prefix.extend(chunk)
    header = bytes(prefix)
    if header == b"\x1f\x8b":
        if stream.seekable():
            stream.seek(0)
            return _read_bounded_gzip(stream, max_bytes)
        return _read_bounded_gzip(cast("BinaryIO", _PrefixedReader(header, stream)), max_bytes)
    payload = bytearray(header)
    while len(payload) <= max_bytes:
        chunk = stream.read(min(65_536, max_bytes + 1 - len(payload)))
        if not isinstance(chunk, (bytes, bytearray)):
            raise TypeError("mzML binary stream must return bytes")
        if not chunk:
            break
        payload.extend(chunk)
    if len(payload) > max_bytes:
        raise ValueError("mzML payload exceeds the research limit")
    return bytes(payload)


def _finalize_spectra(output: list[Spectrum]) -> tuple[Spectrum, ...]:
    if len({spectrum.spectrum_id for spectrum in output}) != len(output):
        raise ValueError("mzML spectrum IDs must be unique")
    return tuple(output)


def parse_mzml(  # noqa: PLR0915 - parser keeps XML state and safety checks together.
    source: bytes | bytearray | BinaryIO,
    *,
    max_bytes: int = 256 * 1024 * 1024,
    max_spectra: int = 100_000,
) -> tuple[Spectrum, ...]:
    """Decode bounded m/z and intensity arrays from one mzML document."""
    if (
        type(max_bytes) is not int
        or type(max_spectra) is not int
        or not 0 < max_bytes <= 512 * 1024 * 1024
        or not 0 < max_spectra <= 1_000_000
    ):
        raise ValueError("research limits are outside supported bounds")
    root = ElementTree.fromstring(_payload(source, max_bytes))
    if _local(root.tag) != "mzML":
        raise ValueError("mzML root element is required")
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
        precursor_ambiguous = False
        for cv in element.findall("{*}cvParam"):
            accession = cv.attrib.get("accession")
            if accession == "MS:1000511":
                ms_level = int(cv.attrib["value"])
            elif accession == "MS:1000016":
                value = float(cv.attrib["value"])
                retention = value * 60.0 if cv.attrib.get("unitName") == "minute" else value
        if ms_level < 1:
            raise ValueError("mzML MS level must be positive")
        if retention is not None and (not math.isfinite(retention) or retention < 0):
            raise ValueError("mzML retention time must be finite and non-negative")
        selected_ions: set[tuple[float | None, int | None]] = set()
        for selected_ion in element.findall(".//{*}selectedIon"):
            ion_mz: float | None = None
            ion_charge: int | None = None
            seen_ion_mz = False
            seen_ion_charge = False
            for cv in selected_ion.findall("{*}cvParam"):
                accession = cv.attrib.get("accession")
                if accession == "MS:1000744" and cv.attrib.get("value") is not None:
                    if seen_ion_mz:
                        raise ValueError("selected ion declares duplicate precursor m/z")
                    seen_ion_mz = True
                    ion_mz = float(cv.attrib["value"])
                elif accession == "MS:1000041" and cv.attrib.get("value") is not None:
                    if seen_ion_charge:
                        raise ValueError("selected ion declares duplicate precursor charge")
                    seen_ion_charge = True
                    ion_charge = int(cv.attrib["value"])
            if ion_mz is not None or ion_charge is not None:
                selected_ions.add((ion_mz, ion_charge))
        if len(selected_ions) > 1:
            precursor_ambiguous = True
        elif selected_ions:
            precursor_mz, precursor_charge = next(iter(selected_ions))
        if precursor_mz is not None and (not math.isfinite(precursor_mz) or precursor_mz <= 0):
            raise ValueError("mzML precursor m/z must be finite and positive")
        if precursor_charge is not None and precursor_charge < 1:
            raise ValueError("mzML precursor charge must be positive")
        arrays = element.findall(".//{*}binaryDataArray")
        mz: tuple[float, ...] = ()
        intensity: tuple[float, ...] = ()
        seen_mz = False
        seen_intensity = False
        for array in arrays:
            accessions = {item.attrib.get("accession") for item in array.findall("{*}cvParam")}
            if "MS:1000514" in accessions and "MS:1000515" in accessions:
                raise ValueError("mzML binary array declares both m/z and intensity roles")
            values = _binary_array(array, max_output_bytes=max_bytes)
            if "MS:1000514" in accessions:
                if seen_mz:
                    raise ValueError("mzML spectrum declares duplicate m/z arrays")
                seen_mz = True
                mz = values
            elif "MS:1000515" in accessions:
                if seen_intensity:
                    raise ValueError("mzML spectrum declares duplicate intensity arrays")
                seen_intensity = True
                intensity = values
        if any(not math.isfinite(value) or value <= 0 for value in mz):
            raise ValueError("mzML m/z values must be finite and positive")
        if any(not math.isfinite(value) or value < 0 for value in intensity):
            raise ValueError("mzML intensity values must be finite and non-negative")
        if len(mz) != len(intensity):
            raise ValueError("mzML m/z and intensity arrays differ in length")
        spectrum_id = element.attrib.get("id", f"scan={len(output) + 1}")
        if (
            not spectrum_id
            or len(spectrum_id) > 256
            or spectrum_id != spectrum_id.strip()
            or any(character.isspace() or ord(character) < 32 for character in spectrum_id)
        ):
            raise ValueError("mzML spectrum IDs must be bounded opaque strings")
        output.append(
            Spectrum(
                spectrum_id,
                ms_level,
                retention,
                mz,
                intensity,
                precursor_mz,
                precursor_charge,
                precursor_ambiguous,
            )
        )
    return _finalize_spectra(output)
