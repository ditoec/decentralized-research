# Code Audit: ComfyUI Noise and Sampler Hooks; Bittensor SN30 and SN23 Validators (2026-11-22)

I read the source code at these commits:

| Repo | Commit | Date | Status |
|---|---|---|---|
| Comfy-Org/ComfyUI | `8b25bbc371b73e876996cf14c917d075d78de2ee` | 2026-11-22 | active |
| womboai/wombo-bittensor-subnet (SN30) | `91b66fe2e58a2508a3e3495ea345e90a676cf842` | 2024-06-18 | **archived** |
| SocialTensor/SocialTensorSubnet (SN23, NicheImage) | `a4a2461b86d8eacc32674969985d032e0ef94fb0` | 2025-03-25 | active (last push) |

The SN30 and SN23 validators currently running on the network may differ from these repo versions. Cite the commit, not "the subnet".

---

## 1. ComfyUI: is the initial noise reproducible?

**Yes. The initial noise is generated on the CPU in float32 from the seed.** `comfy/sample.py`:

```python
def prepare_noise(latent_image, seed, noise_inds=None):
    generator = torch.manual_seed(seed)
    ...
def prepare_noise_inner(latent_image, generator, noise_inds=None):
    return torch.randn(latent_image.size(), dtype=torch.float32, layout=latent_image.layout,
                       generator=generator, device="cpu").to(dtype=latent_image.dtype)
```

KSampler and the custom-sampler `RandomNoise` node (`comfy_extras/nodes_custom_sampler.py`, `Noise_RandomNoise`) both use this path.

**Consequence:** a verifier can recompute x_T **bit-exactly** on any machine, CPU included, given the seed, the latent shape and the torch version. So the check x_T = noise(seed) in E1 is an exact check, not a tolerance check. This should be confirmed across torch versions in RQ1, because the CPU Philox/MT stream is stable within a major version but this has not been verified.

### 1.1 Per-step noise in ancestral and SDE samplers depends on the device

`comfy/k_diffusion/sampling.py`:

```python
def default_noise_sampler(x, seed=None):
    if seed is not None:
        if x.device == torch.device("cpu"):
            seed += 1
        generator = torch.Generator(device=x.device)
        generator.manual_seed(seed)
    ...
    return lambda sigma, sigma_next: torch.randn(x.size(), ..., device=x.device, generator=generator)
```

- The noise injected at each step by `euler_ancestral`, `dpmpp_2s_ancestral`, `dpmpp_sde` and similar samplers is drawn on **the GPU running the job**. It uses a sequential CUDA generator.
- A CPU run uses `seed + 1` **on purpose**, so CPU and GPU streams differ by design.
- PyTorch does not guarantee identical CUDA random streams across GPU models.
- `BrownianTreeNoiseSampler`, used by the SDE samplers, is a separate path.

**Design rule:**
- **Core study:** deterministic samplers only (`euler`, `heun`, `dpmpp_2m`, `ddim`, `lms`, `uni_pc`).
- **Extension:** ancestral samplers, only if the per-step noise is moved to a CPU generator through a custom noise sampler. That is simple to do (pass `noise_sampler=`), and it should be treated as a protocol requirement.

### 1.2 What the per-step hook provides

The `k_callback` in `comfy/samplers.py` (KSAMPLER.sample) forwards `callback(i, denoised, x, total_steps)`. Inside the sampler the callback dictionary is `{'x', 'i', 'sigma', 'sigma_hat', 'denoised'}`, where:
- `x` is the latent **before** step i's update.
- `denoised` is the model's x0-prediction at step i, with classifier-free guidance (CFG) already applied.

`sample_dpmpp_2m` updates the latent as `x_{i+1} = (σ_{i+1}/σ_i)·x_i − expm1(−h)·D_i`, where `D_i` combines `denoised_i` and `denoised_{i−1}`.

**This allows a cheaper and stronger design than WOMBO's (see §2). The provider commits the pairs (x_i, denoised_i) for every step i, plus the final x_T.** The verifier then runs two tiers:
- **Tier A, solver consistency, on all steps, on the CPU, with no UNet:** it recomputes x_{i+1} = Φ_solver(x_i, denoised_i, denoised_{i−1}, σ) and compares. This costs essentially nothing. It catches interpolated, copied or truncated latents and wrong sigma schedules (fewer steps).
- **Tier B, model consistency, at k random steps:** it recomputes `denoised_i = CFG(UNet(x_i, σ_i, cond))` and compares with the committed value under a per-step tolerance τ_i. This costs k/T of the job, plus the CFG doubling, which is already counted in the job. It catches fabricated `denoised` values (a forger who inverts the solver to pass Tier A), cheaper models, distilled models and quantized UNets, to whatever extent RQ2 shows they are separable.

**Caveat:** a full trajectory must be committed. The callback does not see the final latent after the last update, so the custom node also has to capture the sampler's return value. Storage per SDXL step is about 2 × 128 KB in fp16, so about 7.7 MB for 30 steps. Keep it off-chain until the job closes.

### 1.3 Factors for RQ1 and attacks are built-in CLI flags

From `comfy/cli_args.py`:
- **Attacks:** `--fp8_e4m3fn-unet`, `--fp8_e5m2-unet` and `--fp8_e8m0fnu-unet` mean that **attack A2 (an fp8 UNet) takes one flag**. It is realistic and needs no expertise.
- **Precision factor:** `--fp16-unet`, `--bf16-unet`, `--force-fp32`.
- **Attention-backend factor:** `--use-pytorch-cross-attention`, `--use-split-cross-attention`, `--use-quad-cross-attention`, and xformers when installed.
- **Determinism mode:** `--deterministic` ("might not make images deterministic in all cases"). This is the treatment for the deterministic-profile pivot in doc 05 §7.

---

## 2. WOMBO SN30: an existing deployment of step-level checking

**Verdict: the core mechanism of E2 (commit the per-step latents, then re-run k random steps) was deployed on Bittensor by 2024.** It is prior art and must be cited. Its rule is uncalibrated and has never been evaluated against attacks.

**Protocol as implemented:**
1. The miner runs `diffusers` with SDXL and ControlNet. It records `latents` after every step through `callback_on_step_end` (`miner/miner/image_generator.py`). It returns `sha256(frames)` first, then serves the frames for download. This is commit-then-reveal.
2. The validator checks `sha256(frames) == declared hash`, and sets `cheater=True` if they differ (`base_validator/validator.py: is_cheater`).
3. With probability **`RANDOM_VALIDATION_CHANCE = 0.35`** (set by an environment variable, drawn from `os.urandom`), it runs `score_similarity` (`forwarding_validator/similarity_score_pipeline.py`):
   - It requires `frames.shape[0] == num_inference_steps`.
   - It samples **k = 3** step indices using `cryptographic_sample` (os.urandom).
   - For each index, it re-runs **one** UNet step (with ControlNet and CFG) from `frames[i]` and computes `cosine_similarity(flatten(recomputed), flatten(frames[i+1]))`.
   - The score is `max(min_similarity · 0.5 + 0.5, 0)`. The response is **rejected if the score is below 0.85**, meaning the minimum cosine similarity is **below 0.70**.
4. The validator decodes the image itself from `frames[-1]` with the VAE. So the final image is bound to the trajectory by construction.

**Weaknesses relevant to our paper.** These are hypotheses to test in RQ2. They are **not** established results.

- **W1, threshold far too loose.** Cosine similarity on the whole flattened latent, with acceptance at 0.70. Consecutive diffusion latents are highly correlated at every step: early on, both are dominated by the same noise, and late in sampling they barely change. *Hypothesis:* a trivial forgery such as `frames[i+1] := frames[i]` (copying the previous frame), linear interpolation, or a trajectory from an fp8 or distilled model all reach cosine ≥ 0.70. If so, the deployed rule is broken by the cheapest possible attack.
- **W2, no calibration.** The numbers 0.85 and 0.70 are not derived from any measured honest variation across GPUs. No FPR or FNR is reported.
- **W3, x_T is not bound to the seed.** The frames start after step 1, and nothing checks that the initial noise came from the seed. The seed generator is created on `device`, which is the GPU.
- **W4, the reward is weighted, not escrowed.** A failed check gives a score of 0 for that response. There is no forfeiture or bond, so there is no deterrence model.
- **W5, apparent implementation issues.** These need confirming before they are mentioned in the paper:
  - `controlnet_keep[i]` uses a loop variable left over from an earlier loop, so the ControlNet scale may come from the wrong step.
  - The pairing of step index and timestep (`index = i+1` with frames `(i, i+1)`) should be checked for an off-by-one error.
  - The per-step noise for ancestral schedulers is regenerated by consuming `index-1` random draws on the GPU generator.

**Ethics.** The repo is archived. Test only offline against the published code at that commit. If the deployed validator still behaves the same way, disclose to WOMBO before publication.

---

## 3. NicheImage SN23: full re-execution with an embedding check

`services/rewarding/cosine_similarity_compare.py` (`CosineSimilarityReward`):
- The validator **regenerates the whole image**, which is E0.
- It embeds the validator's image and the miner's image with **CLIP ViT-B/16** (`vit_base_patch16_clip_384.laion2b_ft_in12k_in1k`) and computes their cosine similarity.
- The reward is **1.0 if the similarity is above 0.9**, `(sim + 0.1)^3` if it is between 0.4 and 0.9, and 0 otherwise. A miner that returns a black image while the validator's is not black gets 0. A miner that returns a non-black image when the validator's is black gets −5. This is the NSFW filter.
- An alternative in `services/rewarding/hash_compare.py` accepts images whose **perceptual-hash Hamming distance is 6 or less**.

**Weaknesses (hypotheses for RQ2):**
- CLIP-embedding similarity measures *semantic* closeness. Fewer steps, a turbo or distilled model, or a lower resolution followed by upscaling will probably exceed 0.9, because the same prompt and seed give the same composition.
- The cost of verifying is 100% of the job for every audited response.
- Like WOMBO, the thresholds are uncalibrated.

---

## 4. What this changes in the paper (applied to doc 05)

1. **E2 is no longer a new mechanism.** WOMBO deployed per-step spot checks in 2024. The novelty claim moves to:
   - (a) the first **calibrated** evaluation of output-level (SN23-style) and step-level (SN30-style) validation rules against cost-saving attacks, on several consumer GPUs;
   - (b) a **hardened** two-tier trajectory check: Tier A on every step plus Tier B at k random steps, per-step calibrated τ_i, an exact x_T seed binding, and a sampler restriction;
   - (c) the theory for (s, k, p) and deterrence;
   - (d) escrow integration.
2. **New headline experiment (RQ2a):** reproduce the deployed SN30 and SN23 rules faithfully, as at the commits listed above, and attack them with A1–A8 plus the trajectory forgeries:
   - copying the previous frame;
   - interpolation;
   - inverting the solver to fake `denoised`;
   - an fp8 UNet;
   - a turbo-model trajectory.

   A result showing that a deployed rule accepts cheap forgeries is a strong, Q1-grade motivating finding. Our calibrated rule is then the fix, and this is a classic break-and-fix structure.
3. **Protocol requirements fixed by the code audit:**
   - deterministic samplers, or CPU-generated per-step noise;
   - commit (x_i, denoised_i, σ_i) for every step, plus the final x;
   - x_T is checked exactly against the seed.
