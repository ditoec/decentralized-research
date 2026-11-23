# trajver: trajectory commitment and verification

The WP1 instrumentation of the ESJ paper (runbook `docs/07-runbook.md` §3): record a ComfyUI diffusion
trajectory, commit to it with a Merkle root, and verify it with the evidence levels E0, E0-N, E1, E2-W
and E2-H (Tier A + Tier B). Also the forgeries F1–F3, attack configurations A1–A8, run manifests and the
analytical model of manuscript §3-3.

## Setup

```bash
cd code
uv venv --python 3.12 .venv
tools/fetch_comfyui.sh                       # ComfyUI at the pinned commit -> .cache/ComfyUI
uv pip install --python .venv/bin/python -r .cache/ComfyUI/requirements.txt
uv pip install --python .venv/bin/python -e ".[dev,metrics]"
```

Models go in `.cache/models/checkpoints/` (git-ignored). SD1.5:
`v1-5-pruned-emaonly.safetensors`, sha256 `6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa`.

## Tests

```bash
.venv/bin/python -m pytest -q tests/unit          # no model; ~10 s
.venv/bin/python -m pytest -q tests/integration   # SD1.5 on the local GPU; T1, T2, T3 and the rules
```

The unit tests drive a toy analytic denoiser through ComfyUI's real `sample_euler` and `sample_dpmpp_2m`,
so Tier A is checked against the pinned sampler code, not a copy of it.

## Use

```python
from trajver import comfy_env
comfy_env.configure([])                 # ComfyUI flags, e.g. ["--fp8_e4m3fn-unet"]; once per process
from trajver.job import JobSpec, Pipeline
from trajver.rules.e2h import draw_steps, e2h
from trajver.rules.e1 import e1
from trajver.thresholds import load

pipe = Pipeline("path/to/model.safetensors")
spec = JobSpec(prompt="...", seed=0, steps=30, sampler="euler")
samples, traj = pipe.run(spec)          # provider side
traj.save("trajectory.safetensors")     # returns the Merkle root

th = load()                             # dev defaults; experiments load the frozen thresholds_v1.json
steps = draw_steps(traj.T, th["k"], b"slot-hash|job-id")
replay = lambda states, sigmas: pipe.replay_denoised(spec, states, sigmas)
verdict = e2h(traj, spec.sampler, replay, steps, th, e1_verdict=e1(traj, pipe, spec, None, th))
```

Every model call made by `trajver` runs inside `comfy_env.pinned_batching()`: see finding 1 in runbook §3.

## Layout

| Path | Contents |
|---|---|
| `trajver/` | The library (see the runbook §3 table) |
| `comfyui_trajectory/` | ComfyUI custom node `KSamplerTrajectory`; symlink into `ComfyUI/custom_nodes/` |
| `tools/` | `fetch_comfyui.sh`; `dev_w1.py` (early look at hypothesis W1) |
| `tests/` | `unit/` (no model), `integration/` (SD1.5) |
| `program/`, `orchestrator/` | Later milestones: Anchor escrow, orchestrator |
