# M27-08 replay integrity

M27-08 replay now recomputes the retirement result from the result-bound request
and compares the complete canonical JSON projection. A caller cannot alter a
package or finding, recompute only the outer result digest, and have the forged
result accepted. Authorization/evaluation failures are sanitized as replay
failures. The ABI, provisional status, retirement semantics, and scientific
claim ceiling are unchanged.

Retirement activity is derived from the explicit `DependencyMigration.status` enum. The
caller-declared dependency identifier remains opaque, so an identifier containing `active` does
not produce an activity finding, while `IN_PROGRESS` always does. This keeps the emitted
abstention and replay digest bound to governed migration state rather than label text.
