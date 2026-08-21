# M12 standalone API transport boundaries

The M12-01 through M12-08 standalone FastAPI adapters now enforce their
declared byte ceilings at the ASGI transport boundary. Previously each route
called `await request.body()` and only then invoked its strict JSON loader.
That allowed an oversized `Content-Length` or streamed body to be fully
materialized before the contract's limit was checked.

Every M12 adapter now uses the shared request-size middleware. Validation and
execution routes use the module's canonical request ceiling. Each `/verify`
route is selected as a result path and independently uses the module's
canonical result ceiling. Oversized requests are rejected with HTTP 413 and
never reach JSON decoding, authorization, or service execution.

This is transport/resource hardening only. It does not change the provisional
M12 schemas, endpoint names, replay contracts, or scientific claim ceilings.
The regression matrix covers all eight request routes and all eight verify
routes using oversized declared `Content-Length` values, which exercises
rejection before body parsing without allocating a large test payload.
