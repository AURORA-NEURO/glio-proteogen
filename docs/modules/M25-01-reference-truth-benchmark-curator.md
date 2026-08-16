# M25-01 reference truth and benchmark curator

## Boundary

M25-01 receives only caller-declared metadata and artifact references. Its
parent target is `proteotype`; it does not emit the parent. The implementation
does not import an M24-08 runtime or invent an upstream result media type.

## Contract and runtime closure

- nine strict JSON-schema contracts expose request, output, entry, endpoint,
  inclusion, adjudication, configuration, package, and finding shapes;
- request closure enforces unique reference/control/source IDs and complete
  inclusion/adjudication coverage;
- package closure binds marked challenge entries exactly and recomputes its
  lock digest without self-reference;
- deterministic results bind request digest, status-derived result identifier,
  result payload digest, provenance, evidence, seven uncertainty dimensions,
  and explicit limitations;
- denied controls fail closed before source traversal;
- strict parse-once plugin, FastAPI, Typer, service, and replay paths share
  the same typed contract.

## Safe behavior

Pending or reviewed adjudication, rejected included material, malformed input,
denied controls, duplicate keys, digest tampering, package-lock tampering, and
unsupported metadata do not become negative biological findings. They remain
abstained or rejected with sanitized errors and human-review signaling.
