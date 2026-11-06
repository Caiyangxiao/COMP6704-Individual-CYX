"""Assemble the final English paper from the saved, audited 90-run study."""
from pathlib import Path
import csv
import json
import shutil
from hashlib import sha256

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DATA = ROOT / "results/full_study"
ASSETS = HERE / "assets"
ASSETS.mkdir(exist_ok=True)


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


groups = csv_rows(DATA / "analysis/grouped_results.csv")
runs = csv_rows(DATA / "summary.csv")
assert len(runs) == 90
assert sum(r["stationary"] == "True" for r in runs) == 73
assert sum(r["global_hit"] == "True" for r in runs) == 26
# The report's test count must come from the current, durable test audit.
# Refuse stale counts if tests change after that audit was recorded.
TEST_AUDIT = ROOT / "audits/revision_20261105/unit_tests.json"
unit_test_audit = json.loads(TEST_AUDIT.read_text(encoding="utf-8"))
assert unit_test_audit.get("passed") is True, "The recorded unit-test audit did not pass"
unit_test_count = unit_test_audit.get("tests_run")
assert type(unit_test_count) is int and unit_test_count > 0, "Invalid audited unit-test count"
test_sources = unit_test_audit.get("test_sources")
assert isinstance(test_sources, dict) and test_sources, "The audit must identify its test sources"
assert set(test_sources) == {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("*.py")}, "Test inventory changed after its audit"
for relative_path, expected_hash in test_sources.items():
    source = ROOT / relative_path
    assert source.is_file(), f"Audited test source is missing: {relative_path}"
    assert sha256(source.read_bytes()).hexdigest() == expected_hash, f"Test source changed after its audit: {relative_path}"
pages = []


def page():
    blocks = []
    pages.append(blocks)
    return blocks


def add(blocks, kind, text="", **kwargs):
    blocks.append(dict(kind=kind, text=text, **kwargs))


def h(b, text): add(b, "h", text)
def p(b, text): add(b, "p", text)
def small(b, text): add(b, "small", text)
def eq(b, key, number): add(b, "eq", key=key, number=number)
def table(b, headers, rows, widths): add(b, "table", headers=headers, rows=rows, widths=widths)
def figure(b, key, width, maxheight): add(b, "figure", key=key, width=width, maxheight=maxheight)
def caption(b, text): add(b, "caption", text)


def sci(value, digits=3):
    x = float(value)
    return f"{x:.{digits-1}e}" if abs(x) < .001 or abs(x) >= 1e4 else f"{x:.{digits}g}"


def integer(value): return str(int(float(value)))


def grouped(problem):
    rows = []
    for d in (2, 10, 20):
        for m in ("GD", "CG", "BFGS"):
            g = next(g for g in groups if g["problem"] == problem and int(g["dimension"]) == d and g["method"] == m)
            rows.append([str(d), m, g["stationary_count"] + "/" + g["global_hit_count"],
                         integer(g["nit_median"]),
                         integer(g["nfev_median"]) + "\n[" + integer(g["nfev_min"]) + ", " + integer(g["nfev_max"]) + "]",
                         integer(g["njev_median"]) + "\n[" + integer(g["njev_min"]) + ", " + integer(g["njev_max"]) + "]",
                         sci(g["f_value_median"]) + "\n[" + sci(g["f_value_min"]) + ", " + sci(g["f_value_max"]) + "]"])
    return rows


b = page()
add(b, "title", "Stationarity, Evaluation Cost, and Solution Quality\nin Nonconvex Unconstrained Optimization")
add(b, "subtitle", "A controlled CPU comparison of GD, PR+ conjugate gradient, and BFGS")
add(b, "author", "Yangxiao Cai  |  Student ID: 26023041r\nCOMP6704 Individual Assignment, Fall 2026\nPrimary direction: Unconstrained Optimization")
h(b, "Abstract")
p(b, "We compare Armijo gradient descent (GD), safeguarded nonlinear conjugate gradient (CG), and BFGS on Rosenbrock and Rastrigin through 90 controlled CPU solves. Dimensions 2, 10, and 20 each use five paired initial points and fixed stopping criteria. In the recorded Windows reference run, 73/90 runs meet the gradient tolerance and 26/90 meet the global-objective tolerance: 47 meet only the gradient criterion, while 17 meet neither. On Rosenbrock, CG and BFGS attain the global-objective target in 14/15 and 12/15 cases; GD reaches the iteration cap in all 15 cases. On Rastrigin, 43/45 runs meet the gradient tolerance, but none meets the global-objective target. Endpoint diagnostics and comparisons conditional on CG and BFGS both meeting the global-objective target separate local convergence, evaluation cost, and final objective quality. Complete traces support this empirical distinction.")
h(b, "1. Introduction and scope")
p(b, "Smooth unconstrained optimization is a useful setting for studying how descent directions, line searches, curvature information, and stopping rules interact. It also exposes a practical ambiguity: software may report successful termination at a point with a small gradient even when its objective remains far from the global minimum. Comparing iteration counts alone can conceal both this difference in solution quality and the work spent rejecting trial steps.")
p(b, "This individual project belongs to Unconstrained Optimization. The variables range over all of real Euclidean space, and the objectives are nonconvex. The group project selected the Convex Optimization direction; the present investigation instead studies local algorithms outside convexity. Rosenbrock supplies a curved valley and coupled coordinates, while Rastrigin supplies many attraction basins and separable oscillations. Both have known global objective value zero, making stationarity and global-objective quality independently measurable [7, 8].")
p(b, "Three questions guide the comparison. First, which methods reach the common gradient tolerance within a fixed accepted-update budget? Second, what function and gradient evaluation costs accompany their outcomes across dimensions and paired starts? Third, when termination is unsuccessful or non-global, what do the saved traces and endpoint curvature actually support? The design fixes the implementations and settings before comparing all 90 outcomes, including failures.")
add(b, "url", "Code and data", url="https://github.com/Caiyangxiao/COMP6704-Individual-CYX")
small(b, "The repository's README.md provides setup, verification, and reproduction commands. The PDF also embeds an offline snapshot as COMP6704_reproducibility.zip.")

b = page()
h(b, "2. Literature review and connection to the course")
p(b, "Classical foundation. Nocedal and Wright [1] organize smooth unconstrained methods around a search direction and an inexact line search. Their treatment connects first-order stationarity, descent, quasi-Newton curvature, and local convergence. These concepts provide the classroom framework here: an update can decrease the objective while remaining slow, and a necessary first-order condition becomes sufficient for global optimality only under additional structure such as convexity. Our nonconvex functions deliberately remove that sufficiency.")
p(b, "Step selection and memory. Armijo's early work [2] established a sufficient-decrease approach to choosing step lengths. GD uses the current negative gradient, making its behavior easy to audit but sensitive to geometry. Nonlinear CG carries information from the preceding search direction. Gilbert and Nocedal [3] analyze globally convergent CG variants with appropriate safeguards and line searches on smooth nonconvex problems. Such results depend on the precise variant and assumptions; they do not imply that an arbitrary Polak–Ribiere implementation or a positive beta alone ensures descent. The PR+ implementation used here therefore warrants source-level identification.")
p(b, "Quasi-Newton methods. Fletcher's variable-metric development [4] is part of the foundation of BFGS. BFGS learns curvature from successive displacements and gradient differences instead of forming an analytic Hessian. This can improve local progress, at the cost of matrix storage and updates. Positive-definite inverse-Hessian approximations yield descent directions in exact arithmetic, but neither this property nor a Wolfe line search certifies a global minimizer on a nonconvex objective. Implementation details and finite precision remain relevant when a solver stops near its tolerance.")
p(b, "Recent theory. Jin, Jiang, and Mokhtari [5] obtain explicit non-asymptotic rates for BFGS with Armijo–Wolfe line search under strong convexity and smoothness; additional regularity supports stronger rate statements. Their analysis clarifies the gap between qualitative convergence and finite-iteration performance. Strong convexity is absent globally in our tests, so these rates provide context rather than a theorem for the recorded runs. Mannel [6] studies a modified, globalized L-BFGS and Barzilai–Borwein framework for nonconvex unconstrained optimization, using cautious updates and conditions supporting stationarity of cluster points. This is a different algorithm from ordinary full-memory SciPy BFGS. Its relevance is that nonconvex guarantees require carefully designed safeguards, rather than a change of terminology.")
table(b, ["Source / line of work", "Relevance to this study", "Boundary of the comparison"], [
    ["Armijo [2]; textbook [1]", "Sufficient decrease; descent-lemma reasoning", "Finite backtracking caps can terminate early"],
    ["Gilbert–Nocedal [3]", "Nonlinear CG safeguards and nonconvex analysis", "Identify the actual PR+ implementation"],
    ["Jin et al. [5], 2024", "Finite-time BFGS analysis with inexact line search", "Strong-convexity rates do not apply globally here"],
    ["Mannel [6], 2025", "Nonconvex globalization of limited-memory methods", "Modified L-BFGS is not the tested full BFGS"]
], [.28, .35, .37])
p(b, "Study position. The controlled comparison distinguishes satisfaction of the gradient criterion, objective quality, and evaluation cost using complete traces. Version-pinned SciPy documentation and source [7] determine the implemented CG and BFGS behavior. Known optima and transparent benchmark geometry make discrepancies between success labels and objective quality directly measurable; Section 9 discusses the limits of this design.")

b = page()
h(b, "3. Formal problem and objective geometry")
p(b, "We solve min f(x) over x in R^d, with d in {2, 10, 20}; no feasibility constraints or projections are imposed. Write g_k = grad f(x_k), use the Euclidean norm throughout, and denote the known global objective by f* = 0. The two benchmark models are")
eq(b, "models_R", 1)
eq(b, "models_A", 2)
p(b, "The Rastrigin expression is algebraically equivalent to 10d + sum_i[x_i^2 - 10 cos(2 pi x_i)] [8]. The sine-squared form avoids cancellation between large constants near zero. Rosenbrock uses SciPy's rosen and rosen_der; Rastrigin has the analytic derivative")
eq(b, "gradients_A", 3)
p(b, "For Rosenbrock, each term indexed by i contributes -400 x_i(x_{i+1}-x_i^2) + 2(x_i-1) to derivative component i and 200(x_{i+1}-x_i^2) to component i+1. The implementation accumulates all adjacent contributions. Before solving, central differences at 12 nonstationary test points check both gradients, using h_i = 10^-6 max(1, |x_i|) and componentwise absolute and relative tolerances 10^-5. All 12 checks pass; those checks are outside solver evaluation counts.")
p(b, "Known optima and nonconvexity. Both models are sums of nonnegative terms. Rosenbrock reaches zero only at the all-ones vector for d >= 2; Rastrigin reaches zero only at the zero vector. In two-dimensional Rosenbrock, the Hessian at (0,1) is diag(-398,200), so the function is not convex. This point is not a saddle point: its gradient is (-2,200), which is nonzero. For Rastrigin the Hessian is diagonal with entries 2 + 40 pi^2 cos(2 pi x_i); a coordinate equal to 1/2 yields negative curvature. Negative curvature at an arbitrary point establishes nonconvexity, not stationarity.")
p(b, "The coupled Rosenbrock valley makes curvature vary strongly with direction. Rastrigin is separable, yet its oscillatory terms produce many local basins; coordinatewise independence therefore does not make a local descent method a global solver. Both functions are smooth and coercive, so bounded objective sublevels are compact. Their gradients have suitable local Lipschitz bounds on bounded regions, but Rosenbrock's gradient is not globally Lipschitz over all of R^d. At the two-dimensional Rosenbrock global minimizer, the Hessian has eigenvalues approximately 0.39936 and 1001.60064, giving condition number about 2508. This local ill-conditioning is consistent with slow GD progress; it is not a rate estimate for the full nonlinear trajectory. These distinctions matter when stating descent guarantees.")
h(b, "4. Algorithms and implementation")
h(b, "4.1 Gradient descent with Armijo backtracking")
eq(b, "gd_armijo", 4)
p(b, "GD is implemented directly. Every iteration starts again at alpha_0 = 1, halves the trial step with tau = 0.5, and accepts the first point satisfying (4), with c1 = 10^-4. At most 50 reductions follow the initial trial, and the minimum step is 10^-12. A rejected trial never updates x. Nonfinite values, an unchanged floating-point point, and an exhausted line search receive explicit failure statuses. The accepted-update limit is 5000; all function calls at rejected trial points still count.")

b = page()
h(b, "4.2 Safeguarded nonlinear conjugate gradient")
eq(b, "cg", 5)
p(b, "CG uses scipy.optimize.minimize(method='CG') with analytic gradients. Equation (5) is the PR+ direction recurrence, initialized with p_0 = -g_0 [3, 7]. SciPy 1.13.1 adds a sufficient-descent acceptance check for the proposed next direction: the inner product of the next direction and gradient must not exceed -0.01 times the squared gradient norm, unless the gradient target is already met. PR+ truncation alone does not guarantee this property. This safeguard is not a fixed periodic restart. Both SciPy methods use the strong-Wolfe conditions")
eq(b, "wolfe", 6)
p(b, "Here 0 < c1 = 10^-4 < c2 = 0.4 < 1. The same constants reduce one source of variation between CG and BFGS, although their search directions and internal trial sequences still differ. Function and gradient counts consequently remain necessary measurements.")
h(b, "4.3 Full-memory BFGS")
p(b, "BFGS uses scipy.optimize.minimize(method='BFGS'), p_k = -H_k g_k, and H_0 = I. With displacement s_k and gradient change y_k as defined below, the inverse-Hessian update is [1, 4]")
eq(b, "bfgs", 7)
h(b, "4.4 Ideal Armijo GD stationarity bound")
p(b, "For GD, assume f is bounded below by f_inf and its gradient is L-Lipschitz with one uniform constant L on all relevant trial segments. Coercivity bounds accepted iterates; bounded gradients there and trial steps no larger than one contain the trial segments in a compact region, where smoothness supplies such an L. The descent lemma makes any alpha <= 2(1-c1)/L sufficient for (4). With ideal unlimited backtracking from one, an accepted alpha is at least the lower bound below. Summing (4) over K updates gives")
eq(b, "gd_bound", 8)
p(b, "Thus ideal Armijo GD has a standard O(epsilon^-2) accepted-update bound for finding an iterate with gradient norm at most epsilon under these assumptions. This is a stationarity result, not a global-optimality result. The actual finite iteration, trial, and minimum-step limits can stop a run before it reaches that target; the asymptotic statement does not override its recorded failure.")
h(b, "4.5 BFGS curvature implication")
p(b, "For a descent direction p_k and an accepted strong-Wolfe step, (6) gives the curvature inequality")
eq(b, "curvature", 9)
p(b, "In exact arithmetic, (7) therefore preserves positive definiteness from H_0=I, even when the true Hessian is indefinite. This curvature property does not ensure global optimality or prevent finite-precision failure. The strong-convexity rates in [5] do not apply globally here; CG convergence likewise requires its line-search and regularity hypotheses.")

b = page()
h(b, "5. Experimental protocol, costs, and auditing")
table(b, ["Component", "Fixed protocol"], [
    ["Design", "2 functions x 3 dimensions x 5 paired starts x 3 methods = 90 solves"],
    ["Initialization", "Seed 20261105; PCG64 with SeedSequence([seed, objective_index, d]); coordinates uniform on [-2,2] for Rosenbrock and [-3,3] for Rastrigin"],
    ["Stopping", "Euclidean gradient norm <= 10^-6; at most 5000 accepted updates"],
    ["SciPy options", "CG/BFGS: c1=10^-4, c2=0.4, norm=2, gtol=10^-6, maxiter=5000. BFGS: H0=I, xrtol=0; default c2=0.9 is overridden. No analytic Hessian or damping."],
    ["Arithmetic / environment", "float64; Python 3.12.8, NumPy 1.26.4, SciPy 1.13.1; Windows 11; sequential CPU solves; BLAS/OpenMP thread variables set to 1"],
    ["Hardware record", "Intel64 Family 6 Model 191 Stepping 2; 24 logical CPUs reported; no GPU used"],
    ["Independent outcomes", "Native solver status; S: finite result and ||grad f||_2 <= 10^-6; G: finite result and |f-f*| <= 10^-6"]
], [.22, .78])
p(b, "The intervals above generate initial points only; they do not constrain subsequent iterates. Each function-dimension pair has its own random stream, and each of its five saved starts is shared across methods. This pairing controls starting difficulty without asserting that five points represent all possible initializations. The two tolerances define different questions. Native solver_success and S happen to agree for these 90 runs, but remain distinct fields; G is a known-objective target rather than a mathematical certificate of exact optimality.")
p(b, "Evaluation accounting. A wrapper counts every actual raw objective and gradient call made by a solver, including rejected line-search trials and trials in a failed terminal search. Calls avoided by SciPy's cache are not invented. The wrapper counts must equal SciPy's returned nfev/njev. Callbacks only copy accepted coordinates and snapshot counters; they do not reevaluate f or g. Each trace contains an initial event with counters zero, one event per accepted update, and a terminal event. Initial plot diagnostics and every recorded objective/gradient norm are filled offline from raw functions, outside the counters and timer. Thus the initial point can appear at nfev=0 without making the solver's own initial evaluation free.")
p(b, "The study records 80,605 events: 80,425 accepted updates and 180 initial/terminal events. Solver time covers evaluations, updates, and event capture, excluding imports, offline diagnostics, file I/O, and plotting. The sum of measured solver times is 26.915 s, rather than total pipeline wall time. Timing is secondary because these small problems are sensitive to Python, callback, and scheduling overhead. Figures stop at each actual endpoint; no curve is extended after termination, and log-display floors never change raw values.")
table(b, ["Method", "Direction / update arithmetic", "Solver state"], [
    ["GD", "O(d) per direction; line-search calls additional", "O(d)"],
    ["PR+ CG", "O(d) per direction; line-search calls additional", "O(d)"],
    ["BFGS", "O(d^2) direction; standard low-rank update O(d^2); tested SciPy dense-product update O(d^3)*", "O(d^2)"]
], [.16, .67, .17])
caption(b, "Table 1. Algorithmic work excludes objective/gradient calls, each O(d) for these models. *SciPy 1.13.1 forms A1 @ H @ A2 using generic dense products [7]; O(d^3) uses conventional dense arithmetic, not an empirical scaling fit. Storing K d-dimensional trace points adds O(Kd) space for every method.")
p(b, f"Audit checks cover pairings, trace structure, monotone counters, GD sufficient decrease, endpoints, native counts, and source hashes. All {unit_test_count} unit tests and the independent full-study validator pass.")

b = page()
h(b, "6. Results: Rosenbrock")
table(b, ["d", "Method", "S/G", "Updates\nmedian", "nfev\nmedian [range]", "njev\nmedian [range]", "Final f\nmedian [range]"], grouped("rosenbrock"), [.045, .10, .065, .105, .205, .18, .30])
caption(b, "Table 2. Rosenbrock, five starts in every row. S and G are counts out of five, not a ratio. Ranges are minima and maxima; failed runs remain included. Complete update and time ranges are in grouped_results.csv. Scientific notation is rounded only for display.")
figure(b, "paper_rosenbrock_convergence", 507, 185)
caption(b, "Figure 1. Gradient norm against cumulative function evaluations for all five starts in each dimension. Colors denote methods; circles meet S and crosses do not. The x-axis is symlog with a linear region at zero; each curve stops at termination. The horizontal dashed line is 10^-6.")
p(b, "Budget and convergence. CG and BFGS meet the gradient criterion in all 15 Rosenbrock runs each; GD meets it in none. Every GD run accepts all 5000 permitted updates, with no failed line search. The final gradient medians are 5.31e-3, 4.30e-2, and 1.26e-1 at d=2,10,20, well above tolerance. Accepted-step medians are 1/512, 1/1024, and 1/1024, while median trial counts per accepted step are 10, 11, and 11. Their large function counts reflect repeated trial rejection as well as slow progress in the valley. The geometry and reset-to-one policy offer a plausible explanation; this study has no ablation to isolate their causal contributions.")

b = page()
h(b, "7. Results: Rastrigin")
table(b, ["d", "Method", "S/G", "Updates\nmedian", "nfev\nmedian [range]", "njev\nmedian [range]", "Final f\nmedian [range]"], grouped("rastrigin"), [.045, .10, .065, .105, .205, .18, .30])
caption(b, "Table 3. Rastrigin uses the same definitions and all-run convention as Table 2. In the final row, nfev and njev have equal medians but different ranges because one terminal search adds unequal function and gradient counts.")
p(b, "Stationarity and objective quality separate sharply. GD and CG each meet S in 15/15 runs; BFGS meets S in 13/15. None of the 45 runs meets G. Hence 43 runs meet the gradient criterion while missing the global-objective target. Across each dimension, CG uses fewer function evaluations than GD: medians 19,19,19 versus 276,305,305. BFGS's corresponding medians are 12,39,86. These counts describe function evaluations to the observed endpoints; differing final objective values prevent an equal-quality cost comparison.")
p(b, "The paired final objectives in Figure 2 show how rankings depend on the outcome. At d=2, GD obtains a lower f than both other methods on four of the five starts, despite using more function evaluations. On start 1 it returns f=0.994959 with 313 function evaluations, compared with CG's 4.974790 using 24 and BFGS's 7.959662 using 10. All three methods meet the gradient criterion. For this starting point, GD achieves the lowest final objective value but requires the most function evaluations. Raw Rastrigin objectives add contributions across coordinates; their increase across dimensions alone is not evidence of worsening per-coordinate quality.")
h(b, "7.1 The two BFGS precision-loss terminations")
table(b, ["20D start", "Updates", "nfev / njev", "Final gradient norm", "Final f"], [
    ["3", "26", "117 / 105", "8.73821e-6", "41.78821486"],
    ["4", "21", "45 / 45", "1.00023457e-6", "64.67220759"]
], [.14, .13, .20, .28, .25])
p(b, "Both retain SciPy status=2 and its precision-loss message. At start 3 the last accepted event has counts 59/59; the terminal event adds 58 function and 46 gradient evaluations without accepting a new point. This directly exposes unsuccessful terminal trial work that iteration counts omit. At start 4 there are no extra terminal calls, and the last accepted objective change rounds to zero. Its final gradient norm is only 0.02346% above the threshold, but it remains a failure under the fixed rule. Relaxing the threshold after seeing the result would change the protocol.")
p(b, "The common message does not uniquely identify an internal mechanism for each run. Failed line-search progress and finite-precision resolution are consistent with the saved evidence, but the traces do not expose every internal scalar. The analytic derivations and independent checks provide no evidence of a gradient implementation error. Finite checks do not exclude every numerical problem. Both outcomes are included in the final row of Table 3 and shown as crosses in Figure 2.")

b = page()
h(b, "8. Paired outcomes and endpoint interpretation")
figure(b, "paper_rastrigin_quality_convergence", 507, 318)
caption(b, "Figure 2. All Rastrigin starts. Top: final raw f, with faint vertical segments connecting the range of three outcomes for each shared start. Bottom: gradient norm against cumulative nfev, with symlog x and log y. Colors denote methods; circles meet S and crosses do not. Compare objective quality within each dimension because f is additive. Curves end at their true termination, including unsuccessful runs.")
h(b, "8.1 Non-global Rosenbrock endpoints")
table(b, ["d / start / method", "Final f", "Gradient norm", "Minimum Hessian eigenvalue"], [
    ["10 / 4 / CG", "3.9865791123", "9.56589e-7", "0.501273"],
    ["10 / 4 / BFGS", "3.9865791123", "9.63817e-7", "0.501273"],
    ["10 / 5 / BFGS", "3.9865791123", "8.78814e-8", "0.501273"],
    ["20 / 1 / BFGS", "3.9866238543", "4.44622e-7", "0.498755"]
], [.28, .22, .20, .30])
caption(b, "Table 4. The four Rosenbrock endpoints meeting S but missing G. Hessian spectra are computed offline and excluded from solve time and evaluation counts.")
p(b, "These four endpoints explain why 30 Rosenbrock runs meet the gradient criterion but only 26 meet the global-objective target. Positive numerical Hessian eigenvalues together with small gradients support the interpretation that the solvers finish near non-global local minima. At an approximate point, those quantities are numerical evidence, not an exact proof of a stationary local minimizer. Several methods can therefore converge convincingly while legitimately differing from the known global optimum. The contrast with GD's 15 budget-exhausted runs also separates convergence to a different basin from failure to reach stationarity within the budget.")

p(b, "Evaluation cost at comparable quality. BFGS's nfev medians rise from 48 to 114 to 175, while CG's rise from 56 to 434 to 709. Different counts of runs meeting G prevent an equal-quality comparison of these unconditional medians. Restricting to shared initial points for which both methods meet G leaves 5, 3, and 4 pairs for d=2,10,20; the median ratios of function evaluations, nfev(CG)/nfev(BFGS), are 1.24, 2.97, and 3.91. These median ratios favor BFGS in function evaluations; they do not measure wall time or describe starts where either method misses G. CG meets G in 14/15 runs overall versus BFGS in 12/15.")

b = page()
h(b, "9. Discussion, limitations, and reproducibility")
p(b, "Interpretation of the three questions. First, in the recorded Windows reference run, 73/90 runs meet the common gradient criterion, with failures concentrated in Rosenbrock GD and two 20D Rastrigin BFGS runs. Second, function and gradient counts reveal costs hidden by accepted-update counts; the terminal 58/46 extra calls are a concrete example. The median ratios favor BFGS in function evaluations on the selected Rosenbrock pairs where both methods meet G, whereas CG uses fewer function evaluations than GD to its observed Rastrigin stationary endpoints. Third, final f and endpoint diagnostics show that meeting the gradient criterion does not imply meeting the global-objective target: 47 runs meet S while missing G. These observations connect descent and curvature concepts from the course to actual solver behavior.")
p(b, "Limits of the evidence. The study includes only two synthetic functions, three dimensions up to 20, and five fixed starts per setting. Its observed fractions are not estimated population success probabilities. Dimensions and changing random starts vary together, so trends across dimensions are descriptive. The experiment neither establishes asymptotic scaling nor measures the practical memory limit of BFGS. A single implementation and one set of line-search constants also cannot isolate the effects of direction, step selection, initialization, tolerance, and numerical safeguards. Millisecond timings do not justify a universal fastest-method claim, and conditioning cost ratios on both methods attaining G creates an explicitly selected subset.")
p(b, "Platform scope. The tables describe the recorded Windows run. Pinning NumPy and SciPy versions does not guarantee identical floating-point paths across operating systems, Python builds, processors, or linked numerical libraries. Small arithmetic differences can change line-search decisions, evaluation counts, and classifications near the strict 10^-6 threshold. A different execution path does not, by itself, invalidate the saved Windows records. Such differences require trace-level diagnosis; this study does not isolate a platform-specific cause.")
p(b, "Useful follow-up work would vary GD's initial trial-step policy under the same starts, sweep the stopping tolerance and iteration budget, and compare damped or limited-memory quasi-Newton variants using a larger test collection. Multi-start global search would address basin selection but would answer a different question from this fixed local-method comparison. A real-data smooth objective would improve external relevance while usually removing access to a known global optimum. These are future experiments, not results claimed here.")
h(b, "9.1 Reproducibility and access")
p(b, "Start with README.md in the GitHub repository linked on page 1. The PDF also embeds an offline snapshot as COMP6704_reproducibility.zip, with packaging_verification.json attached separately. Historical Windows-to-Windows comparisons, archived unit tests, and read-only data/source checks are dated and scoped separately; they establish neither a new formal experiment nor cross-platform numerical identity.")
h(b, "10. Conclusion")
p(b, "Under the fixed protocol, convergence to a small-gradient point did not imply a small global-objective gap. Rosenbrock favored CG and BFGS over this GD configuration within the iteration budget, but both sometimes reached non-global near-stationary points. On Rastrigin, all global-objective targets were missed despite 43/45 runs meeting the gradient criterion; GD occasionally obtained better objective values while using more function evaluations. The two BFGS precision-loss terminations were retained, including one just above tolerance. These results support separate reporting of stationarity, objective quality, costs, and failure modes.")

b = page()
h(b, "References")
refs = [
    ("[1] J. Nocedal and S. J. Wright. Numerical Optimization, 2nd ed. Springer, 2006. DOI: 10.1007/978-0-387-40065-5.", "https://link.springer.com/book/10.1007/978-0-387-40065-5"),
    ("[2] L. Armijo. Minimization of functions having Lipschitz continuous first partial derivatives. Pacific Journal of Mathematics, 16(1):1–3, 1966.", "https://msp.org/pjm/1966/16-1/pjm-v16-n1-p01-p.pdf"),
    ("[3] J. C. Gilbert and J. Nocedal. Global convergence properties of conjugate gradient methods for optimization. SIAM Journal on Optimization, 2(1):21–42, 1992. DOI: 10.1137/0802003.", "https://doi.org/10.1137/0802003"),
    ("[4] R. Fletcher. A new approach to variable metric algorithms. The Computer Journal, 13(3):317–322, 1970. DOI: 10.1093/comjnl/13.3.317.", "https://doi.org/10.1093/comjnl/13.3.317"),
    ("[5] Q. Jin, R. Jiang, and A. Mokhtari. Non-asymptotic global convergence analysis of BFGS with the Armijo-Wolfe line search. Advances in Neural Information Processing Systems 37:16810–16851, 2024. DOI: 10.52202/079017-0536. Author version: arXiv:2404.16731, revised January 8, 2025.", "https://arxiv.org/abs/2404.16731"),
    ("[6] F. Mannel. A globalization of L-BFGS and the Barzilai–Borwein method for nonconvex unconstrained optimization. Journal of Optimization Theory and Applications, 204, Article 47, 2025. DOI: 10.1007/s10957-024-02565-5.", "https://link.springer.com/article/10.1007/s10957-024-02565-5"),
    ("[7] SciPy developers. SciPy 1.13.1: minimize-CG and minimize-BFGS reference documentation and optimization tutorial; scipy/optimize/_optimize.py, tag v1.13.1. Version-specific implementation and stopping/line-search options. Accessed November 5, 2026.", "https://github.com/scipy/scipy/blob/v1.13.1/scipy/optimize/_optimize.py"),
    ("[8] S. Surjanovic and D. Bingham. Virtual Library of Simulation Experiments: Test Functions and Datasets—Rastrigin Function. Simon Fraser University. Accessed November 5, 2026.", "https://www.sfu.ca/~ssurjano/rastr.html"),
]
for text, url in refs:
    add(b, "reference", text, url=url)
small(b, "Version-specific option references supporting [7]:")
add(b, "url", "CG documentation", url="https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-cg.html")
add(b, "url", "BFGS documentation", url="https://docs.scipy.org/doc/scipy-1.13.1/reference/optimize.minimize-bfgs.html")
small(b, "The course page limit includes this reference list. The PDF uses the official NeurIPS 2025 style with a course-specific notice.")

for key in ("paper_rosenbrock_convergence", "paper_rastrigin_quality_convergence"):
    source = DATA / "analysis/paper_figures" / (key + ".png")
    if source.is_file():
        shutil.copyfile(source, ASSETS / source.name)
inputs = [DATA / "summary.csv", DATA / "analysis/grouped_results.csv", DATA / "analysis/run_diagnostics.csv", DATA / "metadata.json", TEST_AUDIT]
content = {"title": "Stationarity, Evaluation Cost, and Solution Quality in Nonconvex Unconstrained Optimization", "author": "Yangxiao Cai", "student_id": "26023041r", "track": "Unconstrained Optimization", "pages": pages, "source_sha256": {str(f.relative_to(ROOT)).replace("\\", "/"): sha256(f.read_bytes()).hexdigest() for f in inputs}}
(HERE / "content.json").write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Created English paper content: {len(pages)} planned pages")
