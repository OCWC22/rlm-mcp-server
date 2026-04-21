"""Dataset loaders for paper-aligned evaluation tasks."""

from __future__ import annotations

from .browsecomp import load_tasks as load_browsecomp_tasks
from .longbench import load_tasks as load_longbench_tasks
from .oolong import load_tasks as load_oolong_tasks
from .sniah import load_tasks as load_sniah_tasks

DATASET_LOADERS = {
    "sniah": load_sniah_tasks,
    "oolong": load_oolong_tasks,
    "browsecomp": load_browsecomp_tasks,
    "longbench": load_longbench_tasks,
}


def load_dataset_tasks(dataset: str, **kwargs):
    key = dataset.strip().lower()
    if key not in DATASET_LOADERS:
        known = ", ".join(sorted(DATASET_LOADERS))
        raise ValueError(f"unknown dataset {dataset!r}; expected one of: {known}")
    return DATASET_LOADERS[key](**kwargs)
