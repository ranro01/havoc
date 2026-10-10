"""Generate synthetic runbooks, postmortems, metrics, logs and labelled incidents."""

import argparse

from havoc import config
from havoc.datagen import generate

p = argparse.ArgumentParser()
p.add_argument("--n", type=int, default=30, help="number of labelled incidents")
p.add_argument("--seed", type=int, default=42)
a = p.parse_args()
print(generate(config.data_dir(), a.n, a.seed), "->", config.data_dir())
