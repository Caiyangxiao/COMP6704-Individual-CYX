# COMP6704 Individual Assignment: CPU Experiments in Unconstrained Optimization

**Author:** CAI Yangxiao  
**Student ID:** 26023041r  
**Primary direction:** Unconstrained Optimization  
**Topic:** Stationarity, evaluation cost, and solution quality for GD, nonlinear PR+ conjugate gradient, and BFGS on nonconvex Rosenbrock and Rastrigin functions.

**[Download the final report (PDF)](https://github.com/Caiyangxiao/COMP6704-Individual-CYX/raw/refs/heads/main/submission/CAI%20Yangxiao%2B26023041r.pdf)**

The primary access point is the [project repository](https://github.com/Caiyangxiao/COMP6704-Individual-CYX). Begin with the `README.md` at the repository root. The ZIP embedded in the submitted PDF provides an offline snapshot of the source, original experimental data, and reproduction instructions.

The saved Windows reference study contains **90 solves**: two functions, dimensions 2, 10, and 20, five paired starting points per setting, and three methods. **73/90** runs meet the gradient criterion and **26/90** meet the global-objective target; 47 meet only the gradient criterion, and 17 meet neither.

The report, validation tools, and delivery tools were revised on **2026-11-05**. The documentation and file-rebuild revisions on **2026-11-06** did not rerun the 90-solve study or the historical 50-test suite. The original results, starting points, configurations, and statistical tables are retained. Identify a repository checkout by its commit and the offline submission snapshot by its archive manifest; rebuilding local files does not publish them to GitHub.

## 1. Access, local artifacts, and evidence scope

The repository is the primary route to the code and reproduction instructions. For offline access, the PDF submitted to Canvas contains exactly two attachments: `COMP6704_reproducibility.zip` and `packaging_verification.json`. Download the original PDF and extract them through a PDF reader's attachment panel. The first attachment contains the code, original experimental data, and reproduction commands. After extracting it, begin with the `README.md` at the extracted project root, follow Section 2 to install the environment, and use Section 3 to validate the saved study.

The following paths describe local build artifacts; their listing does not imply that each file is submitted to Canvas separately.

| Local build artifact | Contents |
|---|---|
| `submission/CAI Yangxiao+26023041r.pdf` | English report using the official NeurIPS 2025 style; at most 10 pages including references and less than 20 MB |
| `submission/COMP6704_reproducibility.zip` | Runnable source, the original 90-solve data, analyses, tests, report sources, and build materials; byte-identical to the attachment with the same name in the PDF |
| `submission/Filename_update_notes.txt` | Notes for the current filename and download-access revision |
| `submission/COMP6704_revision_audits.zip` | Historical audit bundle from the 2026-11-05 revision, retaining its validation, delivery, and packaging records |
| `submission/filename_file_checks.json` | Checks of the actual renamed PDF, attachments, and files for the current filename revision |

`packaging_verification.json` is generated after packaging and becomes the PDF's second attachment. **It is not included in the code ZIP that it verifies.** The source archive excludes `.venv`, caches, the delivered PDF, the archive itself, old delivery directories, and additional numerical rerun directories.

Evidence is separated by date and purpose:

| Path | Meaning and scope |
|---|---|
| `results/full_study/metadata.json` | Environment, threads, initialization, and original source SHA-256 values for the Windows reference study |
| `audits/history/windows_exact_reproduction_20261105.json` | Historical exact comparison of 90 Windows runs against Windows reference results, retained as original bytes; its temporary candidate directory no longer exists |
| `audits/history/packaging_before_revision_20261105.json` | Historical packaging check predating the 2026-11-05 revision, retained as original bytes; it does not verify the current archive |
| `audits/final_review_20261105/`, `paper_source/review_record.json` | Earlier review snapshots with their original scope, source hashes, and test counts; they are not current pass records |
| `audits/revision_20261105/unit_tests.json`, `audits/revision_20261105/unit_tests.log` | Historical unit-test results from the 2026-11-05 revision, including the actual count, test-source hashes, and log |
| `audits/revision_20261105/current_validation.json` | Historical read-only data, source, and environment validation from the 2026-11-05 revision, using the schema described in Section 3 |
| `audits/revision_20261105/source_hash_probe.json` | Historical source-byte and line-ending-equivalence checks from the 2026-11-05 revision |
| `audits/revision_20261105/preservation_check.json` | Historical preservation check for the original results and protected statistical materials from the 2026-11-05 revision |
| `audits/revision_20261105/baseline_evidence/evidence_inventory.json` | Inventory of evidence available before that revision, with its provenance and scope |
| `paper_source/polish_record_20261106.json`, `submission/polish_file_checks.json` | Records of the earlier wording and file-rebuild revision on 2026-11-06; retained as prior revision evidence |
| `paper_source/repository_record_20261106.json` | Historical record of the repository-access and English-documentation revision before the author-name change, including its preservation and review checks and compiled source before attachment embedding |
| `paper_source/author_record_20261106.json` | Historical author-name and build checks before the filename change, including the compiled source before attachment embedding |
| `paper_source/filename_record_20261106.json` | Current pre-packaging filename, download-access, and build checks, including the compiled source before attachment embedding; included in the code ZIP |
| `submission/packaging_verification.json` | Temporary extraction, membership, and hash checks for the current code ZIP; an external working record and the PDF's second attachment |
| `submission/repository_file_checks.json` | Historical checks of the PDF, attachments, and local delivery files before the author-name change |
| `submission/author_file_checks.json` | Historical checks of the PDF, attachments, and delivery files after the author-name change but before the filename change |
| `submission/filename_file_checks.json` | Checks of the actual renamed final PDF, its attachments, and the current local delivery files |

The historical Windows comparison and the 2026-11-05 test results do not represent a new numerical run or cross-platform validation on 2026-11-06. The current filename and download-access review and file checks are recorded separately in `filename_record_20261106.json` and `filename_file_checks.json`; the author-name and repository-access records are retained as historical evidence from before this change. Interpret each record according to its date and stated scope. The source ZIP's `archive_manifest.json` records member sizes and SHA-256 values.

## 2. Installation and interpreter selection

Obtain a working tree either by extracting the offline code ZIP into a new directory or, optionally, by cloning the repository:

```bash
git clone https://github.com/Caiyangxiao/COMP6704-Individual-CYX.git
cd COMP6704-Individual-CYX
```

Git storage and checkout settings can normalize text-file line endings. Use the archived ZIP and its manifest for the byte-preserving historical snapshot; identify a Git working tree by its commit. Line-ending equivalence and numerical agreement are distinct from raw-byte identity.

Run all commands from the project root containing this README, `configs/`, and `cpu_optimization/`. The reference environment uses Python **3.12.8**, NumPy **1.26.4**, SciPy **1.13.1**, and Matplotlib **3.10.0**. `requirements-lock.txt` records the original environment dependencies; `requirements.txt` pins the three main numerical and plotting dependencies.

Windows PowerShell:

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
```

Linux or macOS, using an installed Python 3.12.8 interpreter:

```bash
python3.12 --version
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-lock.txt
```

In subsequent commands, `python` denotes the virtual environment's interpreter. Without activating the environment, use `.\.venv\Scripts\python.exe` on Windows or `.venv/bin/python` on Linux and macOS. WSL can invoke an existing Windows environment through `.venv/Scripts/python.exe`. If the full lock file cannot be installed on a platform, use `requirements.txt` and retain the actual environment record; validation must report any version differences. Absolute paths from the original machine are provenance, not runtime requirements.

Pinned NumPy and SciPy versions do not guarantee identical floating-point paths across operating systems, Python builds, processors, or linked numerical libraries. Small arithmetic differences can change line searches, evaluation counts, and classifications near the strict `1e-6` threshold. This study does not isolate a specific platform-dependent cause. Matching software versions, validating saved data, and reproducing new solver executions are separate forms of evidence.

## 3. Unit tests and read-only validation

```bash
python run_tests_audit.py --output audits/local_check/unit_tests.json
python validate_study.py --results results/full_study --output audits/local_check/current_validation.json
```

Use **`tests_run`** in `unit_tests.json` as the test count, and inspect `passed`, `failures`, `errors`, `skipped`, and the adjacent `.log`. The tests cover gradients, Armijo decrease, budgets and failure states, counters, paired initial points, output protection, raw hashes, and line-ending equivalence. Small temporary unit-test fixtures are not additional formal benchmark experiments.

`validate_study.py` invokes no solver and writes nothing into the reference results directory. Its default output is `audits/current_validation.json`; explicitly using `audits/local_check/` avoids replacing delivered audit evidence. The validator rejects output paths inside `results/` or protected source trees. Its report uses `schema_version=2`:

| Validation domain | Main checks | Pass condition |
|---|---|---|
| `data_internal_integrity` | The 90 summary rows, per-run JSON files and traces, complete design, 30 paired initial points, 12 gradient checks, `nit` and cumulative counts, GD updates and Armijo decrease, endpoint diagnostics, and independent labels | The domain reports `passed=true` with no data errors |
| `source_integrity` | Project sources recorded in the historical metadata and the installed SciPy `_optimize.py`; both raw SHA-256 comparisons and any line-ending-equivalence proof are retained | Every source matches the historical bytes or satisfies the strict equivalence proof; missing files and substantive content changes fail |
| `environment_match` | Historical Python patch version, NumPy, and SciPy versions; separate records of operating system, build, CPU, and thread context | Required versions match; contextual differences are reported separately and do not establish numerical-path or timing equivalence |

Top-level `passed` is the conjunction of all three domains. Top-level `errors` are prefixed by their domain. Differences in operating system, CPU, or thread context are not classified as corruption of saved data, but `platform_context` should be reviewed. Passing this validation does not constitute a new 90-solve study or reproduce wall-clock times. If `results/full_study/analysis/validation.json` exists, it is a retained earlier record and does not replace a new local validation output.

Source validation first compares the current raw bytes with the trusted historical SHA-256 and retains `raw_comparison`. On a mismatch, it may reconstruct uniformly LF or CRLF line endings from the current bytes. A file is classified as `eol_equivalent` only if a reconstruction's SHA-256 **exactly equals the historical raw digest**. The expected digest is not rewritten, and general hash differences are not ignored: byte-order marks, whitespace, final newlines, and code content remain subject to comparison. If raw bytes differ and contain a bare CR, this fallback is rejected. SciPy source differences and required-version mismatches still fail their respective domains.

## 4. Saved data and offline analysis

| Path relative to `results/full_study/` | Contents |
|---|---|
| `summary.csv`, `runs/`, `traces/` | The 90-run summary, per-run JSON files, and event-level CSV traces |
| `initial_points.json` | The 30 saved starting points, shared by all three methods |
| `gradient_checks.json` | Twelve central-difference checks at nonstationary points |
| `config_resolved.json`, `metadata.json` | Fixed protocol, historical environment, provenance, and execution status |
| `analysis/grouped_results.csv` | Eighteen groups with medians and ranges over five starts, retaining failures |
| `analysis/initial_point_comparison.csv`, `analysis/paired_comparisons.csv` | Paired endpoint and evaluation-cost comparisons |
| `analysis/run_diagnostics.csv` | Termination, final-step, and offline curvature diagnostics for every run |
| `analysis/nonstationary_runs.csv`, `analysis/stationary_non_global_runs.csv` | The 17 runs missing the gradient threshold and the 47 runs meeting that threshold but missing the global-objective target |
| `analysis/analysis_summary.json` | Summary statistics at full stored precision |
| `analysis/analysis_provenance.json`, metadata in figure directories | Source, input, and display-parameter provenance for later analyses and figures |

The reference study contains **80,605 trace events and 80,425 accepted updates**. Logarithmic display floors affect visualization only. Curves end at actual termination, are not extended by carrying forward endpoints, and retain failed runs. Offline Hessian calculations and other diagnostics are excluded from solver budgets.

To regenerate statistics and figures without writing into the delivered reference tree, first copy the data to a new working directory:

```bash
python -c "import shutil; shutil.copytree('results/full_study', 'work/offline_rebuild')"
python analyze_results.py --results work/offline_rebuild --plot
python make_paper_figures.py --results work/offline_rebuild --output work/offline_rebuild/analysis/paper_figures
```

`copytree` refuses an existing destination; select a new directory for subsequent executions. These commands analyze and plot saved data without invoking the solvers.

## 5. Optional numerical reproduction in a new directory

Readers may execute the following steps to produce a new numerical study. **These formal solver commands were not executed for this documentation revision.**

```bash
python run_experiments.py --config configs/full_study.json --output results/full_study_repeat01 --threads 1
python validate_study.py --results results/full_study_repeat01 --output audits/local_check/repeated_validation.json
python paper_source/verify_reproduction.py --reference results/full_study --candidate results/full_study_repeat01 --output audits/local_check/reproduction_comparison.json
```

The runner refuses to overwrite a nonempty output directory; choose a new name if necessary. A smaller check can use `configs/demo_2d.json` with another new output directory: two functions, one two-dimensional starting point each, and three methods produce six solves.

The strict comparator matches saved numerical results and traces by `run_id`, excluding elapsed times and timestamps. Evidence for a new environment requires actually running and comparing its results; bitwise identity is not presumed. `--threads 1` sets BLAS and OpenMP thread variables in the process before NumPy is imported, without changing system settings. Methods execute sequentially.

## 6. Fixed protocol, logging, and computational costs

| Item | Fixed setting |
|---|---|
| Functions and dimensions | Rosenbrock and Rastrigin; dimensions 2, 10, and 20 |
| Starting points | Five per setting; base seed `20261105`; `PCG64 / SeedSequence([seed, objective_index, dimension])` |
| Initialization distributions | Rosenbrock: `Uniform[-2,2]` per coordinate; Rastrigin: `Uniform[-3,3]` per coordinate; these intervals generate starts and do not constrain subsequent iterates |
| Stopping criterion | float64; Euclidean gradient norm `<=1e-6`; at most 5000 accepted updates |
| Independent global-objective label | Finite result with `abs(f_final-f_star)<=1e-6`; both functions have `f_star=0` |

- **GD:** Direct implementation of Armijo backtracking with `alpha0=1, c1=1e-4, tau=0.5` and minimum step `1e-12`. At most 50 reductions follow the initial trial, giving at most 51 trials; the minimum step can stop the search earlier. Failed steps do not update the coordinates. Nonfinite values and floating-point stagnation receive explicit statuses.
- **CG:** SciPy 1.13.1 nonlinear PR+ CG with analytic gradients and `norm=2, gtol=1e-6, c1=1e-4, c2=0.4`. The implementation adds a sufficient-descent check for the next direction beyond PR+ truncation; its version-specific source defines the precise behavior.
- **BFGS:** SciPy 1.13.1 full-memory BFGS with analytic gradients, an identity initial inverse-Hessian approximation, and `norm=2, gtol=1e-6, c1=1e-4, c2=0.4, xrtol=0`. The configured `c2` overrides the library default of `0.9`.

Rosenbrock uses SciPy `rosen/rosen_der`. Rastrigin uses the algebraically equivalent stable expression `sum(x_i**2 + 20*sin(pi*x_i)**2)`, with gradient `2*x_i + 20*pi*sin(2*pi*x_i)`. Central-difference checks use `h_i=1e-6*max(1,abs(x_i))` and componentwise `atol=rtol=1e-5`, outside the solver budget. The analytic derivations and independent checks provide no evidence of a gradient implementation error. Finite checks do not exclude every numerical problem.

All actual solver calls to the objective and gradient pass through counters, including rejected trials and unsuccessful terminal searches. Values reused from SciPy's cache do not count as new objective or gradient evaluations. Wrapper counts must agree with the returned `nfev/njev`.

| Event | Interpretation |
|---|---|
| `initial` | `iteration=nfev=njev=0`; displayed diagnostics are filled offline, while the solver's own initial evaluations count normally |
| `accepted` | One accepted update; coordinates and existing cumulative counters are copied without additional objective or gradient evaluations in the callback |
| `terminal` | Final coordinates and complete counters, without increasing `nit`; failed trials may increase counters without changing the coordinates |

Solver timing includes initialization, trials, updates, and uniform event capture. It excludes imports, offline diagnostics, plotting, and file I/O. Native `solver_success/solver_status/solver_message`, the common `stationary` label, and `global_hit` are retained independently. In the Windows reference study, `solver_success` and `stationary` both count 73 runs, but represent different criteria. All 15 Rosenbrock-GD runs exhaust the update budget. Two 20-dimensional Rastrigin BFGS runs terminate with precision loss and miss the common gradient threshold. A small gradient does not establish global optimality, and meeting the objective threshold is not a mathematical certificate of exact optimality.

GD and CG have `O(d)` direction and state costs. A standard efficient BFGS direction and low-rank update require `O(d²)` arithmetic. **The tested SciPy 1.13.1 implementation** updates its matrix through generic dense products `A1 @ H @ A2`, requiring `O(d³)` under conventional dense arithmetic; its state and direction calculation remain `O(d²)`. These costs exclude line-search evaluations and logs. Each objective or gradient evaluation is `O(d)` for these models, and saving K points of dimension d adds `O(Kd)` storage and copying work. Equal iteration limits are not equal computational budgets. Timings at these small dimensions do not establish asymptotic scaling or a universally fastest method.

## 7. Rebuilding and packaging the official-style report

The numerical experiments do not require document dependencies. To rebuild the report, install:

```bash
python -m pip install -r requirements-report.txt
```

Also install XeLaTeX through TeX Live or MiKTeX, or install Tectonic, and make the selected engine available as a command. The engine is not distributed in the archive; initial compilation may download packages. `paper_source/template/neurips_2025.sty` remains the official unmodified style, with a course notice set in the main document. The PDF uses US Letter paper, a 5.5 by 9 inch text block, and 10 pt text with 11 pt baseline spacing. Acceptance depends on the compiled output.

Edit `paper_source/create_content.py` to generate `content.json`; equation sources are in `equations.json`. Content generation requires a passing `audits/revision_20261105/unit_tests.json` whose `test_sources` hashes still match the current tests, and reads the actual test count from that record. Missing or stale records stop generation. The local checks in Section 3 write to `audits/local_check/` and do not replace the delivered historical audit.

For Tectonic, execute the following from the project root:

```bash
python paper_source/create_content.py
python paper_source/generate_latex.py
python -c "from pathlib import Path; Path('submission/_latex').mkdir(parents=True, exist_ok=True)"
tectonic --keep-logs --outdir submission/_latex paper_source/template/report.tex
python paper_source/package_reproducibility.py --dry-run
python paper_source/package_reproducibility.py --verification-output submission/packaging_verification.json
python paper_source/package_reproducibility.py --verify-only --verification-output submission/packaging_verification.json
python paper_source/build_final_report.py --latex-pdf submission/_latex/report.pdf --packaging-report submission/packaging_verification.json
```

The LaTeX generator checks the saved-data provenance. The final builder checks the compiled PDF's source fingerprint, page count, file size, byte consistency of all archive members with the current project, and attachment bytes. Finalize the content, README, and pre-packaging records before packaging, then embed the code ZIP and its packaging record to avoid circular dependencies.

The packager preserves original member bytes and verifies the seven original solver-related source files against their historical raw digests. If read-only validation establishes line-ending equivalence but packaging requires different original bytes, retain the discrepancy and recover trusted original bytes rather than changing the expected hash. The current packaging record does not enter its own code archive. The 2026-11-05 audit bundle and earlier 2026-11-06 polish, repository-access, and author-name records remain historical; checks of the current physical files are recorded in `submission/filename_file_checks.json`.

For an independent layout preview:

```bash
python paper_source/build_final_report.py --no-attachment --latex-pdf submission/_latex/report.pdf
```

Preview output is written to `submission/_preview/` without replacing the final delivery. Embedded attachments count toward the final PDF's 20 MB limit. Analysis, read-only validation, document generation, and packaging do not rerun the formal numerical study.

## 8. Main entry points

| Path | Responsibility |
|---|---|
| `cpu_optimization/objectives.py`, `cpu_optimization/solvers.py`, `cpu_optimization/experiment.py` | Objectives and gradients, algorithms and counters, paired starts, and raw outputs |
| `cpu_optimization/analysis.py` and plotting modules | Statistics, termination diagnostics, and figures from saved results |
| `run_experiments.py` | Numerical experiments in a new output directory |
| `run_tests_audit.py`, `tests/` | Unit tests and durable test audits |
| `validate_study.py`, `provenance_integrity.py` | Read-only validation in three domains and strict source-byte/line-ending checks |
| `analyze_results.py`, `plot_results.py`, `make_paper_figures.py` | Offline analysis and plotting |
| `configs/`, `requirements*.txt` | Fixed configurations and dependencies |
| `results/full_study/`, `audits/`, `paper_source/` | Original study, scoped evidence, and report sources |

Theory and recent literature are cited in the report. Implementation references include the SciPy 1.13.1 [CG documentation](https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-cg.html), [BFGS documentation](https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-bfgs.html), and [corresponding source](https://github.com/scipy/scipy/blob/v1.13.1/scipy/optimize/_optimize.py).
