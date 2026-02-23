# AutoAdv (MVP Backend Scaffold)

This repository contains a minimal, framework-agnostic backend core for **AutoAdv**:

- create and manage ads,
- attach ad targets (Discord channels),
- run a scheduler tick that sends ads at the configured interval,
- enforce plan limits,
- track send logs with retries and idempotency.

## Quick start

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Project layout

- `src/autoadv/models.py` — dataclasses and enums
- `src/autoadv/service.py` — ad management and plan-limit checks
- `src/autoadv/scheduler.py` — scheduler tick, retries, duplicate-send protection
- `tests/test_scheduler.py` — unit tests for critical flows

## API mapping

The service layer maps directly to your MVP API intents:

- `create_ad(...)` → `POST /ads`
- `start_ad(...)` → `PUT /ads/:id/start`
- `pause_ad(...)` → `PUT /ads/:id/pause`
- `delete_ad(...)` → `DELETE /ads/:id`

A real web framework can call these methods directly.
