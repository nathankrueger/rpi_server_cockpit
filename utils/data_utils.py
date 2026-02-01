"""Data processing utilities."""


def lttb_downsample(data, threshold):
    """
    Downsample data using Largest Triangle Three Buckets (LTTB) algorithm.

    This algorithm preserves the visual shape of the data by selecting points that
    form the largest triangles, capturing peaks, valleys, and trends effectively.

    Args:
        data: List of tuples (timestamp, value)
        threshold: Target number of datapoints in output

    Returns:
        Downsampled list of tuples (timestamp, value)
    """
    if len(data) <= threshold or threshold < 3:
        return data

    # Always include first and last points
    sampled = [data[0]]

    # Bucket size
    bucket_size = (len(data) - 2) / (threshold - 2)

    for i in range(threshold - 2):
        # Calculate point average for next bucket
        avg_range_start = int((i + 1) * bucket_size) + 1
        avg_range_end = min(int((i + 2) * bucket_size) + 1, len(data))

        avg_x = 0.0
        avg_y = 0.0
        avg_range_length = avg_range_end - avg_range_start

        if avg_range_length > 0:
            for j in range(avg_range_start, avg_range_end):
                avg_x += data[j][0]
                avg_y += data[j][1] if data[j][1] is not None else 0
            avg_x /= avg_range_length
            avg_y /= avg_range_length
        else:
            avg_x = data[-1][0]
            avg_y = data[-1][1] if data[-1][1] is not None else 0

        # Get range for this bucket
        range_offs = int(i * bucket_size) + 1
        range_to = int((i + 1) * bucket_size) + 1

        # Point a (previous selected point)
        point_a_x = sampled[-1][0]
        point_a_y = sampled[-1][1] if sampled[-1][1] is not None else 0

        max_area = -1.0
        max_area_point = range_offs

        # Find point forming largest triangle
        for j in range(range_offs, min(range_to, len(data))):
            point_val = data[j][1] if data[j][1] is not None else 0
            area = abs(
                (point_a_x - avg_x) * (point_val - point_a_y) -
                (point_a_x - data[j][0]) * (avg_y - point_a_y)
            ) * 0.5

            if area > max_area:
                max_area = area
                max_area_point = j

        sampled.append(data[max_area_point])

    sampled.append(data[-1])
    return sampled
