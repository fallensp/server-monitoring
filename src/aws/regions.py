"""Multi-region parallel query utility."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Any


MAX_WORKERS = 10


def query_regions(
    regions: list[str],
    query_fn: Callable[[str], Any],
    max_workers: int = MAX_WORKERS,
) -> dict[str, Any]:
    """Execute a query function across multiple regions in parallel.

    Args:
        regions: List of AWS region names to query
        query_fn: Function that takes a region name and returns results
        max_workers: Maximum number of parallel threads

    Returns:
        Dict mapping region name to query results (or exception if failed)
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_region = {
            executor.submit(query_fn, region): region
            for region in regions
        }

        for future in as_completed(future_to_region):
            region = future_to_region[future]
            try:
                results[region] = future.result()
            except Exception as e:
                results[region] = {"error": str(e), "instances": []}

    return results


def aggregate_results(
    region_results: dict[str, Any],
    key: str = "instances",
) -> list[Any]:
    """Aggregate results from multiple regions into a single list.

    Args:
        region_results: Dict mapping region to results
        key: Key to extract from each region's results

    Returns:
        Combined list of all results across regions
    """
    aggregated = []
    for region, result in region_results.items():
        if isinstance(result, dict) and key in result:
            items = result[key]
            for item in items:
                if isinstance(item, dict):
                    item["region"] = region
            aggregated.extend(items)
        elif isinstance(result, list):
            for item in result:
                if isinstance(item, dict):
                    item["region"] = region
            aggregated.extend(result)
    return aggregated
