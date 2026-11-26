import json

from trajver import analysis_wp2 as A


def run(name, tmp_path, jobs=None):
    d = tmp_path / name
    d.mkdir()
    (d / "summary.json").write_text("{}")
    (d / "manifest.json").write_text("{}")
    jobs = jobs or {"p00001_s0": "a", "p00002_s0": "b"}
    (d / "jobs.jsonl").write_text("".join(json.dumps({"job": k, "image_sha256": v}) + "\n" for k, v in jobs.items()))
    return d


def lv(a, b, tmp_path):
    run(a, tmp_path), run(b, tmp_path)
    rs = {r.run_id: r for r in A.load_runs(tmp_path)}
    return A.level(rs[a], rs[b])


def test_level_rules(tmp_path):
    p = "20261126-wp2-"
    cases = [
        ("ref-sd15-fp16-sdpa-euler-nd-spark4-01", "ref-sd15-fp16-sdpa-euler-nd-spark4-02", "L0"),
        ("ref-sd15-fp16-sdpa-euler-nd-spark5-01", "grid-sd15-bf16-sdpa-euler-nd-spark5-01", "L1"),
        ("ref-sd15-fp16-sdpa-euler-nd-spark5-01", "grid-sd15-bf16-split-euler-nd-spark5-01", None),  # two factors
        ("grid-sd15-bf16-sdpa-euler-nd-spark5-01", "grid-sd15-bf16-split-euler-nd-spark5-01", None),  # no reference
        ("ref-sd15-fp16-sdpa-euler-nd-spark5-01", "grid-sd15-fp16-sdpa-dpmpp_2m-nd-spark5-01", None),  # sampler
        ("ref-sd15-fp16-sdpa-euler-nd-spark5-01", "ref-sd15-fp16-sdpa-euler-nd-spark6-01", "L2"),
        ("l2-sdxl-fp16-sdpa-euler-nd-rtx5090b-01", "ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx5090-01", "L2"),
        ("ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx5090-01", "ref-sdxl-fp16-sdpa-euler-nd-spark5-01", "L3"),
        ("ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx3090-01", "ref-sdxl-fp16-sdpa-euler-nd-spark5-01", "L4"),
        ("ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx3090-01", "ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx4090-02", "L4"),
        ("ref-sdxl-fp16-sdpa-euler-nd-spark5-01", "ref-sd15-fp16-sdpa-euler-nd-spark6-01", None),  # model
    ]
    for i, (a, b, want) in enumerate(cases):
        d = tmp_path / str(i)
        d.mkdir()
        assert lv(p + a, p + b, d) == want, (a, b)


def test_excluded(tmp_path):
    run("20261126-wp2-ref-test-sdxl-fp16-sdpa-euler-nd-rtx4090-02", tmp_path)
    run("20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark4-01", tmp_path)
    run("20261125-wp2-ref-caldev-sdxl-fp16-sdpa-euler-nd-rtx4090-01", tmp_path)
    run("20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark5-01", tmp_path)
    assert [r.run_id for r in A.load_runs(tmp_path)] == ["20261125-wp2-ref-sdxl-fp16-sdpa-euler-nd-spark5-01"]


def test_pixel_equal(tmp_path):
    run("20261126-wp2-ref-sd15-fp16-sdpa-euler-nd-spark5-01", tmp_path, {"p00001_s0": "a", "p00002_s0": "b"})
    run("20261126-wp2-ref-sd15-fp16-sdpa-euler-nd-spark6-01", tmp_path, {"p00001_s0": "a", "p00002_s0": "x",
                                                                       "p00003_s0": "c"})
    out = tmp_path / "lv.csv"
    A.main(["levels", str(tmp_path), "--out", str(out)])
    line = out.read_text().splitlines()[1].split(",")
    assert line[0] == "L2" and line[6] == "pixel_equal" and float(line[7]) == 0.5 and line[8] == "2"
