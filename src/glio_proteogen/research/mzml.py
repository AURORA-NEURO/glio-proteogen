"""Bounded mzML spectrum extraction for research workflows."""

from __future__ import annotations

import base64
import gzip
import struct
import zlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, BinaryIO

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


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _binary_array(element: Element) -> tuple[float, ...]:
    encoded = element.find("{*}binary")
    if encoded is None or not encoded.text:
        return ()
    data = base64.b64decode(encoded.text, validate=True)
    compression = {item.attrib.get("accession") for item in element.findall("{*}cvParam")}
    if "MS:1000574" in compression:
        data = zlib.decompress(data)
    if "MS:1000523" in compression:
        width, fmt = 4, "f"
    elif "MS:1000521" in compression:
        width, fmt = 8, "d"
    else:
        raise ValueError("mzML binary array has no supported precision")
    if len(data) % width:
        raise ValueError("mzML binary array has a partial value")
    return tuple(struct.unpack(f"<{len(data) // width}{fmt}", data))


def _payload(source: bytes | bytearray | BinaryIO, max_bytes: int) -> bytes:
    payload = (
        bytes(source) if isinstance(source, (bytes, bytearray)) else source.read(max_bytes + 1)
    )
    if len(payload) > max_bytes:
        raise ValueError("mzML payload exceeds the research limit")
    if payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
        if len(payload) > max_bytes:
            raise ValueError("decoded mzML payload exceeds the research limit")
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
        for cv in element.findall("{*}cvParam"):
            accession = cv.attrib.get("accession")
            if accession == "MS:1000511":
                ms_level = int(cv.attrib["value"])
            elif accession == "MS:1000016":
                value = float(cv.attrib["value"])
                retention = value * 60.0 if cv.attrib.get("unitName") == "minute" else value
        arrays = element.findall(".//{*}binaryDataArray")
        mz: tuple[float, ...] = ()
        intensity: tuple[float, ...] = ()
        for array in arrays:
            accessions = {item.attrib.get("accession") for item in array.findall("{*}cvParam")}
            values = _binary_array(array)
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
            )
        )
    return tuple(output)
