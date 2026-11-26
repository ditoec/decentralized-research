"""analysis_wp3 on synthetic verify outputs whose answers are known (no real attack data)."""
import csv
import hashlib
import json

import pytest

from trajver import analysis_wp3 as A
from trajver.stats import Z95, cp_upper, wilson

KS = (1, 2, 3, 5, 8)
T = 10


def thresholds(tmp_path, tau8=0.5):
    th = {"version": "thresholds_test", "sampler": "euler", "tier_b_metric": "rel_l2", "k": 3,
          "tau": {str(i): 0.5 for i in range(T)},
          "tau_by_k": {str(k): {"alpha_s": 1 - 0.99 ** (1 / k), "tau": {str(i): (tau8 if k == 8 else 0.5)
                                                                         for i in range(T)}} for k in KS},
          "e0": {"lpips_t_pass": 0.1, "lpips_t_fail": 0.3, "dino_t_pass": 0.9, "dino_t_fail": 0.7}}
    p = tmp_path / "thresholds_test.json"
    p.write_text(json.dumps(th))
    return p, hashlib.sha256(p.read_bytes()).hexdigest()


def gen_run(tmp_path, name, attack, jobs, gpu="NVIDIA GeForce RTX 5090", s=0.5, times=None, faked=None,
            time_field="t_total_s"):
    d = tmp_path / name
    (d / "raw" / "labels").mkdir(parents=True)
    m = {"run_id": name, "node": {"gpu_name": gpu, "hostname": "not-used"},
         "models": [{"filename": "sd_xl_base_1.0.safetensors"}], "prompt_set": {"file": "prompts_test.txt"}}
    if attack == "honest":
        m["sampler"] = "euler"
    else:
        m.update(attack=attack, claimed={"sampler": "euler", "steps": T}, actual={"s": s})
    (d / "manifest.json").write_text(json.dumps(m))
    rows = []
    for n, j in enumerate(jobs):
        rows.append({"job": j, "prompt_id": n + 1, "seed": 0, time_field: (times or {}).get(j, 10.0)})
        if faked is not None:
            (d / "raw" / "labels" / f"{j}.json").write_text(json.dumps({"job_id": j, "faked": faked(j)}))
    (d / "jobs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def verify_run(tmp_path, name, source, attack, th_sha, jobs, verdict=lambda j, ev, k: "pass", per_step=None,
               s=0.5, gpu="NVIDIA GB10"):
    d = tmp_path / name
    d.mkdir()
    (d / "manifest.json").write_text(json.dumps({"run_id": name, "source_run": source, "attack": attack,
                                                 "threshold_file_sha256": th_sha, "node": {"gpu_name": gpu}}))
    rows = []
    for j in jobs:
        base = {"job_id": j, "attack": attack, "s": None if attack == "honest" else s, "retention": "O"}
        rows.append({**base, "evidence": "E1", "k": None, "verdict": verdict(j, "E1", None), "score": None})
        rows.append({**base, "evidence": "E2-H.tierA", "k": None, "verdict": verdict(j, "E2-H.tierA", None),
                     "score": 0.0})
        for k in KS:
            v = verdict(j, "E2-H", k)
            r = {**base, "evidence": "E2-H", "k": k, "verdict": v, "score": 0.0, "tier_b": v,
                 "steps": list(range(k))}
            if per_step:
                r["per_step"] = {str(i): {"rel_l2": x} for i, x in per_step(j).items()}
            rows.append(r)
        rows.append({**base, "evidence": "E2-W", "k": 3, "verdict": verdict(j, "E2-W", 3), "score": 0.9})
    (d / "verdicts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def jobs(n, offset=0):
    return [f"p{i:05d}_s0" for i in range(offset + 1, offset + n + 1)]


def honest_pair(tmp_path, sha, n, gname="20261127-wp3-gen-honest-rtx5090-01", vname="20261127-wp3-verify-honest-01",
                **kw):
    js = ["warmup"] + jobs(n)
    gen_run(tmp_path, gname, "honest", js, **kw)
    return verify_run(tmp_path, vname, gname, "honest", sha, jobs(n))


def read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


# ------------------------------------------------------------------------------------- statistics
def test_wilson_zero_bounds():
    for n in (299, 1000):
        lo, hi = wilson(0, n)
        assert lo == 0.0 and hi == pytest.approx(Z95 ** 2 / (n + Z95 ** 2), rel=1e-12)
    assert wilson(0, 299)[1] == pytest.approx(0.012685, abs=1e-6)   # two-sided Wilson: above 1%
    assert wilson(0, 1000)[1] == pytest.approx(0.0038268, abs=1e-6)
    assert cp_upper(0, 299) == pytest.approx(1 - 0.05 ** (1 / 299), rel=1e-9)  # the runbook's 0-in-299 rule
    assert cp_upper(0, 299) < 0.01 and cp_upper(4, 1000) < 0.01 < cp_upper(5, 1000)


# ------------------------------------------------------------------------------------- honest FPR
@pytest.mark.parametrize("n", [299, 1000])
def test_all_honest_pass(tmp_path, n):
    tp, sha = thresholds(tmp_path)
    v = honest_pair(tmp_path, sha, n)
    th = A.load_thresholds(tp)
    rows = A.table_honest_fpr([A.load_run(v)], th)
    by = {(r[2], r[3], r[4]): r for r in rows}
    assert {r[2] for r in rows} == {"rtx5090->spark", "pooled"}
    for key in [("pooled", "E1", ""), ("pooled", "E2-W", 3), ("pooled", "E2-H", 8), ("rtx5090->spark", "E2-H", 1)]:
        r = by[key]
        assert r[5] == n and r[6] == 0 and r[8] == 0.0
        assert r[10] == pytest.approx(Z95 ** 2 / (n + Z95 ** 2), rel=1e-12)
        assert r[11] == pytest.approx(1 - 0.05 ** (1 / n), rel=1e-9)


# ------------------------------------------------------------------------------------- r_A
def test_known_r_a_per_step(tmp_path):
    """Faked steps 0-4 of 10; steps 0, 1 at 1.0 and 2-4 at 0.1, honest steps at 0.01.
    tau = 0.5 for k <= 5 gives r_A = 2/5; tau = 0.05 at k = 8 gives r_A = 1."""
    tp, sha = thresholds(tmp_path, tau8=0.05)
    hv = honest_pair(tmp_path, sha, 50)
    js = jobs(100)
    gen_run(tmp_path, "20261127-wp3-f3-rtx5090-01", "F3", ["warmup"] + js, faked=lambda j: [0, 1, 2, 3, 4])
    vals = {0: 1.0, 1: 1.0, 2: 0.1, 3: 0.1, 4: 0.1, **{i: 0.01 for i in range(5, T)}}
    av = verify_run(tmp_path, "20261127-wp3-verify-f3-01", "20261127-wp3-f3-rtx5090-01", "F3", sha, js,
                    per_step=lambda j: vals)
    th = A.load_thresholds(tp)
    rows = A.table_rates([A.load_run(av)], [A.load_run(hv)], th)
    r = {(x[0], x[5]): x for x in rows}
    for k in (1, 2, 3, 5):
        assert r[("r_A", k)][6] == 500 and r[("r_A", k)][7] == 200 and r[("r_A", k)][8] == pytest.approx(0.4)
    assert r[("r_A", 8)][8] == 1.0
    # the honest run has no per-step distances: alpha_s from its k = 1 rows (all pass) at the frozen k's tau
    assert r[("honest_alpha_s", 3)][6] == 50 and r[("honest_alpha_s", 3)][7] == 0
    assert "k1_rows" in r[("honest_alpha_s", 3)][12]
    assert r[("r_A", 1)][2] == "0.5" and "20261127-wp3-f3-rtx5090-01" in r[("r_A", 1)][13]


def test_known_r_a_k1_rows(tmp_path):
    """No per-step distances: r_A from the k = 1 verdicts. The k = 1 step is step 0 (see verify_run);
    it is faked in every job, and its Tier B fails in 30 of 100 jobs."""
    tp, sha = thresholds(tmp_path)
    js = jobs(100)
    gen_run(tmp_path, "g", "F3", js, faked=lambda j: [0, 4])
    fails = set(js[:30])
    av = verify_run(tmp_path, "v", "g", "F3", sha, js,
                    verdict=lambda j, ev, k: "fail" if (ev == "E2-H" and j in fails) else "pass")
    rows = A.table_rates([A.load_run(av)], [], A.load_thresholds(tp))
    assert len(rows) == 1 and rows[0][5] == 3 and rows[0][6:9] == [100, 30, 0.3]


# ------------------------------------------------------------------------------------- beta
def test_beta_known_timings(tmp_path):
    tp, sha = thresholds(tmp_path)
    js = jobs(20)
    honest_pair(tmp_path, sha, 20, times={"warmup": 99.0})
    hv = tmp_path / "20261127-wp3-verify-honest-01"
    # attack times 4.0 (beta 0.6) on 15 jobs and 8.0 (beta 0.2) on 5: median 0.6; warm-up 0.1 s dropped
    times = {"warmup": 0.1, **{j: (4.0 if n < 15 else 8.0) for n, j in enumerate(js)}}
    gen_run(tmp_path, "ga", "A1b", ["warmup"] + js, times=times, time_field="t_compute_s")
    av = verify_run(tmp_path, "va", "ga", "A1b", sha, js)
    with pytest.raises(AssertionError):  # honest t_total_s vs attack t_compute_s is not a valid pair
        assert A.table_beta([A.load_run(av)], [A.load_run(hv)], 200)
    # an honest baseline with t_compute_s (attacks.run M-style) on the same card
    gen_run(tmp_path, "gh2", "honest", ["warmup"] + js, time_field="t_compute_s")
    hv2 = verify_run(tmp_path, "vh2", "gh2", "honest", sha, js)
    (row,) = A.table_beta([A.load_run(av)], [A.load_run(hv2)], 2000)
    assert row[:5] == ["A1b", "", "sdxl", "rtx5090", 20]
    assert row[5] == pytest.approx(0.6) and row[8] == 4.0 and row[9] == 10.0 and row[10] == "t_compute_s/t_compute_s"
    assert 0.2 - 1e-9 <= row[6] <= row[5] <= row[7] <= 0.6 + 1e-9
    assert row[12] == "ga" and row[13] == "gh2"


def test_beta_constant(tmp_path):
    tp, sha = thresholds(tmp_path)
    hv = honest_pair(tmp_path, sha, 10)
    js = jobs(10)
    gen_run(tmp_path, "ga", "F3", ["warmup"] + js, times={j: 7.5 for j in js})
    av = verify_run(tmp_path, "va", "ga", "F3", sha, js)
    (row,) = A.table_beta([A.load_run(av)], [A.load_run(hv)], 500)
    assert row[5] == pytest.approx(0.25) and row[6] == pytest.approx(0.25) and row[7] == pytest.approx(0.25)
    assert row[1] == "0.5" and row[10] == "t_total_s/t_total_s"


# ------------------------------------------------------------------------------------- R2.7
def test_partial_sweep_rows(tmp_path):
    tp, sha = thresholds(tmp_path)
    hv = honest_pair(tmp_path, sha, 30)
    sweep = []
    for s, nfail in ((0.25, 3), (0.5, 7)):
        js = jobs(10)
        g = f"g{s}"
        gen_run(tmp_path, g, "F3", js, s=s, faked=lambda j: [0])
        fails = set(js[:nfail])
        sweep.append(verify_run(tmp_path, f"v{s}", g, "F3", sha, js, s=s,
                                verdict=lambda j, ev, k, f=fails: "fail" if (ev == "E2-H" and j in f) else "pass"))
    out = tmp_path / "out"
    A.main(["--honest", str(hv), "--sweep", *map(str, sweep), "--thresholds", str(tp), "--out", str(out),
            "--n-boot", "100"])
    rows = read(out / "fig_r2_7_partial.csv")
    assert list(rows[0])[:7] == ["attack", "s", "k", "n_jobs", "n_detected", "alpha_s", "r_measured"]
    assert len(rows) == 2 * len(KS)
    got = {(r["s"], int(r["k"])): r for r in rows}
    for s, nfail in (("0.25", 3), ("0.5", 7)):
        for k in KS:
            r = got[(s, k)]
            assert r["attack"] == "F3" and r["n_jobs"] == "10" and int(r["n_detected"]) == nfail
            assert float(r["r_measured"]) == pytest.approx(nfail / 10)  # step 0 is faked, k=1 fails = nfail
            assert float(r["alpha_s"]) == pytest.approx(1 - 0.99 ** (1 / 3))  # verify used the k=3 tau for every k
            assert r["run_ids"] == f"g{s};v{s}"


# ------------------------------------------------------------------------------------- end to end
def test_cli_end_to_end(tmp_path):
    tp, sha = thresholds(tmp_path)
    hv = honest_pair(tmp_path, sha, 40)
    js = jobs(40)
    gen_run(tmp_path, "ga", "A8", ["warmup"] + js, times={j: 10.0 for j in js})
    av = verify_run(tmp_path, "va", "ga", "A8", sha, js,
                    verdict=lambda j, ev, k: "pass" if ev == "E2-W" else "fail")
    cmp = tmp_path / "cmp"
    cmp.mkdir()
    (cmp / "20261127-wp3-regen-spark-01__ga.e0.jsonl").write_text("".join(
        json.dumps({"job": j, "prompt_id": 1, "pixel_equal": False, "lpips": 0.6, "dino_cosine": 0.2,
                    "e0n_pass": n < 10}) + "\n" for n, j in enumerate(js)))
    (cmp / "20261127-wp3-gen-honest-rtx5090-01__20261127-wp3-regen-spark-01.e0.jsonl").write_text("".join(
        json.dumps({"job": j, "prompt_id": 1, "pixel_equal": False, "lpips": 0.05, "dino_cosine": 0.95,
                    "e0n_pass": True}) + "\n" for j in js))
    out = tmp_path / "out"
    A.main(["--honest", str(hv), "--attacked", str(av), "--thresholds", str(tp), "--th-sha256", sha,
            "--compare", str(cmp), "--out", str(out), "--n-boot", "100"])
    for f in ("r2_3_sensitivity", "r2_5_acceptance", "r2_6_rates", "r2_4_beta", "fig_r2_7_partial", "honest_fpr"):
        assert (out / f"{f}.csv").exists()
    sens = {(r["evidence"], r["k"]): r for r in read(out / "r2_3_sensitivity.csv")}
    assert sens[("E2-H", "3")]["q"] == "1.0" and sens[("E2-H", "3")]["fpr"] == "0.0"
    assert sens[("E2-W", "3")]["q"] == "0.0" and sens[("E0", "")]["q"] == "1.0" and sens[("E0", "")]["fpr"] == "0.0"
    assert "ga" in sens[("E0", "")]["run_ids"] and "20261127-wp3-regen-spark-01" in sens[("E0", "")]["run_ids"]
    acc = {(r["attack"], r["rule"]): r for r in read(out / "r2_5_acceptance.csv")}
    assert acc[("A8", "E0-N")]["acceptance"] == "0.25" and acc[("A8", "E2-W")]["acceptance"] == "1.0"
    assert acc[("honest", "E0-N")]["acceptance"] == "1.0"
    beta = read(out / "r2_4_beta.csv")
    assert float(beta[0]["beta_median"]) == 0.0
    meta = json.loads((out / "inputs.json").read_text())
    assert meta["thresholds_sha256"] == sha and meta["attacked"] == ["va"]


def test_refuses_other_thresholds(tmp_path):
    tp, sha = thresholds(tmp_path)
    hv = honest_pair(tmp_path, "0" * 64, 5)
    with pytest.raises(SystemExit, match="did not use"):
        A.main(["--honest", str(hv), "--thresholds", str(tp), "--out", str(tmp_path / "o")])


def test_no_host_names_in_outputs(tmp_path):
    tp, sha = thresholds(tmp_path)
    hv = honest_pair(tmp_path, sha, 5)
    out = tmp_path / "o"
    A.main(["--honest", str(hv), "--thresholds", str(tp), "--out", str(out)])
    assert not any("not-used" in p.read_text() for p in out.iterdir())


# ------------------------------------------------------------------------------------- per-k tau
def test_tau_for_per_k(tmp_path):
    from trajver.thresholds import DEV_DEFAULTS, tau_for
    tp, _ = thresholds(tmp_path, tau8=0.05)
    th = A.load_thresholds(tp)
    assert tau_for(th, 2) == 0.5 and tau_for(th, 2, 3) == 0.5 and tau_for(th, 2, 8) == 0.05
    assert tau_for(dict(DEV_DEFAULTS), 2, 8) == DEV_DEFAULTS["tau_default"]  # no tau_by_k: the single tau


def test_e2h_recomputed_with_tau_of_k(tmp_path):
    """Rows in verify.py's format (per_step as floats): a step at 0.1 passes tau = 0.5 (k <= 5)
    and fails tau = 0.05 (k = 8), whatever the row's own verdict says."""
    tp, sha = thresholds(tmp_path, tau8=0.05)
    js = jobs(4)
    gen_run(tmp_path, "g", "honest", js)
    v = verify_run(tmp_path, "v", "g", "honest", sha, js)
    rows = [json.loads(l) for l in (v / "verdicts.jsonl").read_text().splitlines()]
    for r in rows:
        if r["evidence"] == "E2-H":
            r["per_step"], r["tau_k"] = {str(i): 0.1 for i in range(T)}, r["k"]
    (v / "verdicts.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    jv, note = A.job_verdicts(A.load_run(v), A.load_thresholds(tp))
    assert set(jv[("E2-H", 5)].values()) == {"pass"} and set(jv[("E2-H", 8)].values()) == {"fail"}
    assert note[("E2-H", 8)] == "tau_by_k[8]"
