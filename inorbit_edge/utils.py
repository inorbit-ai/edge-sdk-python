import math


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
