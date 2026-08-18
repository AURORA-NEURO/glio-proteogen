# M27-08 replay integrity

M27-08 replay now recomputes the retirement result from the result-bound request
and compares the complete canonical JSON projection. A caller cannot alter a
package or finding, recompute only the outer result digest, and have the forged
result accepted. Authorization/evaluation failures are sanitized as replay
failures. The ABI, provisional status, retirement semantics, and scientific
claim ceiling are unchanged.
