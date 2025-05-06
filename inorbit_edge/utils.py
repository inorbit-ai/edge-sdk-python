import math
from rdp2 import rdp


def encode_floating_point_list(ranges):
    """
    Encodes a list of float numbers (which may contain infinite values) into a
    FloatingPointList which has a compact representation for runs of
    consecutive inf and non-inf values.
    """

    # Encode the numbers in runs of infinite and non-infinite sequences
    last_was_infinite = True
    current_run_length = 0
    runs = []
    values = []
    for r in ranges:
        if (r == math.inf) == last_was_infinite:
            # Current and last were both infinite, or both non-infinite
            current_run_length += 1
        else:
            # Current=inf, last was not inf; switch and output the last run
            runs.append(current_run_length)
            current_run_length = 1
            last_was_infinite = r == math.inf
        # Now process the number (if not infinite)
        if r != math.inf:
            values.append(r)
    # Finally output the last run length
    runs.append(current_run_length)

    # Do some validations for invariants
    if sum(runs) != len(ranges):
        raise Exception(
            "Sum of encoded runs is {:d}, must be equal to original list "
            "length {:d}".format(sum(runs), len(ranges))
        )
    # Only the first element can be 0
    if len(list(filter(lambda x: x <= 0, runs[1:]))) > 0:
        raise Exception("There are zero or negative elements in runs!")
    if sum(runs[1::2]) != len(values):
        raise Exception(
            "Sum of non-inf runs is {:d}, must be equal to number of "
            "encoded values {:d}".format(sum(runs[1::2]), len(values))
        )

    return runs, values


def reduce_path(path: list, maxn: int, epsilon: float) -> list:
    """
    Applies the Ramer-Douglas-Peucker algorithm to reduce the number of points in a
    path.
    If after compression the number of points is still greater than maxn, remaining
    points are uniformly downsampled.

    Args:
        path (list[tuple[float, float]]): List of tuples (x, y) representing points in
            the path.
        maxn (int): Maximum number of points in the reduced path.

    Returns:
        list[tuple[float, float]]: Reduced list of tuples (x, y) representing points in
            the path.
    """
    reduced_path = rdp(path, epsilon=epsilon)
    if len(reduced_path) <= maxn:
        return reduced_path
    return downsample_array(reduced_path, maxn)


def downsample_array(arr: list, maxn: int) -> list:
    """
    Downsamples (any) array to N elements, taking at regular
    intervals. First and last element are always returned (provided N>=2).

    Args:
        arr (list): Array to downsample.
        maxn (int): Maximum number of elements in the downsampled array.

    Returns:
        list: Downsampled array.
    """
    if len(arr) <= maxn or maxn <= 1:
        # It is assumed that _downsample will return a new array,
        # so just save the iterators logic but still return a copy
        return arr[:]

    # Take exactly maxn elements. Select at regular (non-int) intervals
    # maxn-1 of them, and the last one manually.
    return [arr[int(float(i * len(arr)) / (maxn - 1))] for i in range(maxn - 1)] + [
        arr[-1]
    ]
