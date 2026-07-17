# cython: language_level=3, boundscheck=False, wraparound=False, initializedcheck=False, nonecheck=False, cdivision=True, infer_types=True
from __future__ import annotations

from datetime import datetime
from fractions import Fraction
from typing import Optional, Tuple
import time
import math

# -----------------------------
# Logging (optional)
# -----------------------------
QUAD_INTERVAL_LOG_ENABLED = False
QUAD_INTERVAL_LOG_PATH = None
QUAD_INTERVAL_LOG_HANDLE = None
QUAD_INTERVAL_RUN_ID = None

def _quad_interval_log_init():
    global QUAD_INTERVAL_LOG_PATH, QUAD_INTERVAL_LOG_HANDLE, QUAD_INTERVAL_RUN_ID
    if not QUAD_INTERVAL_LOG_ENABLED:
        return
    if QUAD_INTERVAL_LOG_HANDLE is not None:
        return
    stamp = datetime.now().strftime("%m%d_%H%M%S")
    QUAD_INTERVAL_RUN_ID = stamp
    QUAD_INTERVAL_LOG_PATH = f"quad_intervals_{stamp}.csv"
    QUAD_INTERVAL_LOG_HANDLE = open(QUAD_INTERVAL_LOG_PATH, "w", encoding="utf-8", newline="")
    QUAD_INTERVAL_LOG_HANDLE.write(
        "run_id,N_local,x,offset,nM,x_min,x_max,dx,x1r,x2r,flag\n"
    )

def _quad_interval_log_write(N_local, x, offset, nM, x_min, x_max, dx, x1r, x2r, flag):
    if not QUAD_INTERVAL_LOG_ENABLED:
        return
    _quad_interval_log_init()
    if QUAD_INTERVAL_LOG_HANDLE is None:
        return
    QUAD_INTERVAL_LOG_HANDLE.write(
        f"{QUAD_INTERVAL_RUN_ID},{N_local},{x},{offset},{nM},{x_min},{x_max},{dx},{x1r},{x2r},{flag}\n"
    )
# -----------------------------
# Small helpers
# -----------------------------

def y_mod(N: int, t: int) -> int:
    """Exact remainder y(t) = N mod t using your definition."""
    return N % t

Rat = Tuple[int, int]  # (num, den), den > 0, not auto-reduced

# -----------------------------
# Quadratic fitting and solving
# -----------------------------
cdef inline tuple _rat_norm(object num, object den):
    if den == 0:
        raise ZeroDivisionError("zero denominator in rational")
    if den < 0:
        return (-num, -den)
    return (num, den)


cdef inline tuple _rat_add(tuple a, tuple b):
    return _rat_norm(a[0] * b[1] + b[0] * a[1], a[1] * b[1])


cdef inline tuple _rat_sub(tuple a, tuple b):
    return _rat_norm(a[0] * b[1] - b[0] * a[1], a[1] * b[1])


cdef inline tuple _rat_mul(tuple a, tuple b):
    return _rat_norm(a[0] * b[0], a[1] * b[1])


cdef inline tuple _rat_mul_int(tuple a, object k):
    return _rat_norm(a[0] * k, a[1])


cdef inline tuple _rat_div(tuple a, tuple b):
    return _rat_norm(a[0] * b[1], a[1] * b[0])


cdef inline tuple _rat_neg(tuple a):
    return (-a[0], a[1])


cdef inline object _rat_floor(tuple a):
    return a[0] // a[1]


cdef inline object _rat_ceil(tuple a):
    return -((-a[0]) // a[1])


cdef inline object _rat_to_fraction(tuple a):
    return Fraction(a[0], a[1])


cdef inline int _rat_cmp_int(tuple a, object x):
    cdef object lhs = a[0]
    cdef object rhs = x * a[1]
    if lhs < rhs:
        return -1
    if lhs > rhs:
        return 1
    return 0


cdef inline tuple _sqrt_ratio_candidate(object num, object den):
    """
    For q=num/den (den>0), return:
      - flag True + exact sqrt as ratio if q is a perfect-square rational
      - flag False + floor-sqrt-like ratio (isqrt(num_reduced)/isqrt(den_reduced))
    """
    if num < 0:
        return False, (-1, 1)
    cdef object g = math.gcd(abs(num), den)
    cdef object num_r = num // g
    cdef object den_r = den // g
    cdef object sn = math.isqrt(num_r)
    cdef object sd = math.isqrt(den_r)
    return (sn * sn == num_r and sd * sd == den_r), _rat_norm(sn, sd)


cdef inline tuple _eval_quadratic(tuple a, tuple b, object N_local, object x):
    cdef tuple term_a = _rat_mul_int(a, x * x)
    cdef tuple term_b = _rat_mul_int(b, x)
    return _rat_add(_rat_add(term_a, term_b), (N_local, 1))


cdef inline tuple _create_quadratic_rational(object x1, object y1, object x2, object y2, object N_local):
    """Fit y = a x^2 + b x + N through (x1,y1),(x2,y2) with c=N."""
    cdef object dx1 = x1 * x1
    cdef object dx2 = x2 * x2
    cdef object rhs1 = y1 - N_local
    cdef object rhs2 = y2 - N_local

    cdef object D = dx1 * x2 - dx2 * x1
    cdef tuple a = _rat_norm(rhs1 * x2 - rhs2 * x1, D)
    cdef tuple b = _rat_norm(dx1 * rhs2 - dx2 * rhs1, D)
    return a, b


def intrinsic_level1_window(N: int, x: int) -> Tuple[int, int, int, int, int]:
    """Return (q, tL, tR, Ll, Lr) for region where floor(N/t)==q."""
    q = N // x
    if q <= 0:
        return 0, x, x, 0, 0
    tL = (N // (q + 1)) + 1
    tR = (N // q)
    Ll = max(0, x - tL)
    Lr = max(0, tR - x)
    return q, tL, tR, Ll, Lr

def check_next_limits(aF: Rat, bF: Rat, N_local: int, xLeft_minus: int, xRight_plus: int):
    y1 = _eval_quadratic(aF, bF, N_local, xLeft_minus)
    y2 = _eval_quadratic(aF, bF, N_local, xRight_plus)
    if (_rat_cmp_int(y1, xLeft_minus) < 0) or (_rat_cmp_int(y2, xRight_plus) < 0):
        print("ERROR:\tOut of the Limits.")
    return

# ============================================================
# Limited dummy (performance)
# ============================================================
cdef inline object _analyze_discriminant(tuple a, tuple b, object N):
    """For ax^2 + (b-1)x + N = 0, return (r1,r2,sqrtD) if D is perfect square."""
    cdef tuple B = _rat_sub(b, (1, 1))
    cdef tuple D = _rat_sub(_rat_mul(B, B), _rat_mul_int(a, 4 * N))
    cdef object flag
    cdef tuple sqrtD
    flag, sqrtD = _sqrt_ratio_candidate(D[0], D[1])
    if sqrtD[0] < 0:
        return None
    cdef tuple denom = _rat_mul_int(a, 2)
    if denom[0] == 0:
        return None

    cdef tuple negB = _rat_neg(B)
    cdef tuple r1 = _rat_div(_rat_sub(negB, sqrtD), denom)
    cdef tuple r2 = _rat_div(_rat_add(negB, sqrtD), denom)

    if not flag:    # D is not perfect square
        return _rat_ceil(r1), _rat_floor(r2), False
    return _rat_to_fraction(r1), _rat_to_fraction(r2), True


def analyze_discriminant(a: Rat, b: Rat, N: int) -> Optional[Tuple[Fraction | int, Fraction | int, bool]]:
    return _analyze_discriminant(a, b, N)

## -------------------------- GOOD USED FUNCTION --------------------------------
# #Function dummy_limited_old (below) is the classic dummy_limited
# it could have been renamed as dummy_limites_new but keep the same name 
# for not changing the name in the calling arreas.
## --------------------------------------------------------------------------------

## --------------- updated version -------------------------------------
def dummy_check_An_x0_fraction(
    N_local,
    x,
    offset,
    nM,
    return_coeffs: bool = False,
    deadline: float | None = None,
    time_check_every: int = 2048,
    collect_trace: bool = False,
    verbose_roots: bool = False,
    lean_output: bool = False,
    validate_limits: bool = False,
    return_root_details: bool = False,
):
    """
    Like dummy() but scans only dx in [-dx_limit, +dx_limit] (clipped to offset//2),
    and uses a FAST (float-based) approximation for the grid bounds to avoid SymPy cost.

    Notes:
    - Perfect-square discriminant detection remains exact via analyze_discriminant().
    - The L/vertex/R points are for plotting; they do not need exact algebraic roots.
    """
    # Production fast path: keep signature compatibility but avoid auxiliary/debug work.
    x_inDummy, y_inDummy = [], []
    x_zero, y_zero = (), ()
    x_neg, y_neg = (), ()
    x_Roots = []
    x_RootDetails = []
    root_coeffs = ()
    x_left, x_right = 0, 0
    c_val = N_local

    def _pack_result(interval_examined):
        if return_coeffs:
            if return_root_details:
                return (
                    x_inDummy,
                    y_inDummy,
                    x_zero,
                    y_zero,
                    x_neg,
                    y_neg,
                    x_Roots,
                    x_RootDetails,
                    x_left,
                    x_right,
                    interval_examined,
                    root_coeffs,
                )
            return (
                x_inDummy,
                y_inDummy,
                x_zero,
                y_zero,
                x_neg,
                y_neg,
                x_Roots,
                x_left,
                x_right,
                interval_examined,
                root_coeffs,
            )
        if return_root_details:
            return (
                x_inDummy,
                y_inDummy,
                x_zero,
                y_zero,
                x_neg,
                y_neg,
                x_Roots,
                x_RootDetails,
                x_left,
                x_right,
                interval_examined,
            )
        return (
            x_inDummy,
            y_inDummy,
            x_zero,
            y_zero,
            x_neg,
            y_neg,
            x_Roots,
            x_left,
            x_right,
            interval_examined,
        )

    # Hard deadline guard: return immediately if the caller deadline already expired.
    if deadline is not None:
        try:
            if time.perf_counter() >= deadline:
                return _pack_result((None, None))
        except Exception:
            pass
    # level_1_trinomial = get_level1_trinomial(N_local, x, offset)
    ### Find the level 1 QUADRATIC curve.
    ret_lvl1 = analyze_level1_triple_with_shift(N_local, x, offset)

    if ret_lvl1 is not None and ret_lvl1.get("ok", False):
        ### at least 3 points and a clear quadratic curve.
        x_min = ret_lvl1["tL"]
        x_max = ret_lvl1["tR"]
    else:
        ### we have either "1 or 2 points" or bad case 
        #delta = max(1, offset // 2)
        delta = offset // 2
        x_min = x - delta
        x_max = x + delta

    # Corrections.... Are these OK? 
    if x_min < 1:
        x_min = 1
    if x_max < x_min:
        x_max = x_min

    if QUAD_INTERVAL_LOG_ENABLED:
        _quad_interval_log_init()
    ###  I Think that this LOOP has only to run when we have at least 3 points.
    new_win_L, new_win_R  = N_local, 0
    for i, dx in enumerate(range(x_min, x_max+1)):
        if deadline is not None and (time_check_every <= 1 or (time_check_every > 1 and i % time_check_every == 0)):
            try:
                if time.perf_counter() >= deadline:
                    break
            except Exception:
                pass
        x____1, x___0, x__1 = dx - offset, dx, dx + offset
        if x____1 == 0 or x___0 == 0 or x__1 == 0:
            continue
        x_triplet = [x____1, x___0, x__1]
        y_left = N_local % x_triplet[0]
        y_right = N_local % x_triplet[2]
        a_val, b_val = _create_quadratic_rational(x_triplet[0], y_left, x_triplet[2], y_right, N_local)
        #print(f"Trinomial's a,b= {a_val}, {b_val}")
        if a_val[0] < 0:
            #bad_a_atDummy += 1
            continue
        # create_quadratic_Rational returns rational pairs (num,den).
        aF = a_val
        bF = b_val

        # Exact discriminant check for perfect-square cases (cheap-ish and important)
        sol = _analyze_discriminant(aF, bF, c_val)
        #print(f"(Discr::\t{sol})")
        if sol is not None:
            x1r, x2r, IntegerGoodSol = sol
            _quad_interval_log_write(N_local, x, offset, nM, x_min, x_max, dx, x1r, x2r, IntegerGoodSol)
            if IntegerGoodSol:
                x_Roots.extend([x1r, x2r])
                if return_root_details:
                    aF_str = f"{aF[0]}/{aF[1]}"
                    bF_str = f"{bF[0]}/{bF[1]}"
                    x_RootDetails.append((x_triplet[0], x_triplet[2], aF_str, bF_str, i, dx))
                    x_RootDetails.append((x_triplet[0], x_triplet[2], aF_str, bF_str, i, dx))
                if verbose_roots:
                    print(f"Roots Created: {x_Roots}")

            new_win_L, new_win_R = min(x1r,new_win_L) , max(new_win_R, x2r)
            if validate_limits:
                check_next_limits(aF,bF, N_local, x1r-offset, x2r+offset)
        if collect_trace:
            x_vals = [x_triplet[0], x_triplet[1], x_triplet[2]]
            y_vals = [N_local % xx for xx in x_vals]
            x_inDummy.append(x_vals)
            y_inDummy.append(y_vals)

    # NEW TODO return (x_inDummy, y_inDummy), (x_Roots, y_zero), (x_meg=x_vals[1], y_neg=y_vals[1]), interval_examined, aF,bF
    #  n/d (offset=n), path of fractions: n1/d1, n2/d2, ... nk/dk in level k 
    if new_win_L < new_win_R:
        interval_examined = (new_win_L, new_win_R)
    else:
        interval_examined = (None, None)
    return _pack_result(interval_examined)

#----------------------------------- No No No. Wrong process ---------------------------------------
## ---------------------- This is the one which is used --------------------------------------
def analyze_level1_triple_with_shift(N: int, x: int, offset: int = 3,):
    INC = 1
    DEC = -1
    NO_DIRECTION = 0

    if offset < 3:
        return {"ok": False, "reason": "this helper currently supports offset>=3 (uses 3-point triple)", "x": x, "offset": offset}

    candidates = [
        ("center", (x-1, x,   x+1), 0),
        ("left",   (x-2, x-1, x),   -1),
        ("right",  (x,   x+1, x+2), +1),
    ]

    for tag, (t0, t1, t2), shift in candidates:
        if min(t0, t1, t2) <= 0:
            continue

        y0, y1, y2 = y_mod(N, t0), y_mod(N, t1), y_mod(N, t2)
        direction = INC if (y0 < y1 < y2) else (DEC if (y0 > y1 > y2) else NO_DIRECTION)
        if direction != -1 and direction != 1:
            continue

        q_min, tL_min, tR_min, Ll_min, Lr_min = intrinsic_level1_window(N, t1)  ### (denominator=x, x_min, x_max, x_Left, x_Right)
        #q_max, tL_max, tR_max, Ll_max, Lr_max = intrinsic_level1_window(N, x_max)  ### x_Left, x_Right x_nmbers giving the same int division
        x_min, x_max = tL_min, tR_min
        return {
            "ok": True,
            "tL": tL_min, "tR": tR_min, "Ll": Ll_min, "Lr": Lr_min,  # t corresponds to x values, L corresponds to y values
        }

    # If all fail
    return {
        "ok": False,
    }

#############################################################################################
#############################################################################################
