"""No-network preflight, before any score or prediction request."""
from __future__ import annotations
import csv
import gzip
import io
import os
from pathlib import Path
import re
import subprocess

from .security import child_environment

LENGTHS = (16384, 131072, 524288, 1048576)
REQUIRED = ("gene_symbol", "chrom", "pos1", "ref", "alt")


def parse_variants(text, sequence_length=1048576, null_depth=1000):
    if sequence_length not in LENGTHS:
        raise ValueError(f"Input length must be one of {LENGTHS}")
    if not 10 <= null_depth <= 2000:
        raise ValueError("Null depth must be 10–2,000 per variant; default 1,000")
    if len(text.encode()) > 100_000:
        raise ValueError("Input exceeds 100 KB")
    reader = csv.DictReader(io.StringIO(text.strip()), delimiter="\t")
    if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not set(REQUIRED) <= set(reader.fieldnames):
        raise ValueError("TSV requires unique columns: " + ", ".join(REQUIRED))
    if set(reader.fieldnames) - set(REQUIRED) - {"variant_group_id"}:
        raise ValueError("Unknown columns; only the five required columns and variant_group_id are supported")
    rows = []
    for n, raw in enumerate(reader, 1):
        if n > 20 or None in raw or any(raw[k] is None for k in REQUIRED):
            raise ValueError("Enter 1–20 complete, tab-separated rows")
        row = {k: raw[k].strip().upper() for k in REQUIRED}
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_.-]{0,49}", row["gene_symbol"]):
            raise ValueError(f"Row {n}: invalid gene symbol")
        chrom = row["chrom"].removeprefix("CHR")
        if chrom not in {str(i) for i in range(1, 23)} | {"X", "Y"}:
            raise ValueError(f"Row {n}: use a primary chromosome 1–22, X or Y")
        row["chrom"] = "chr" + chrom
        if not row["pos1"].isdigit() or not 1 <= int(row["pos1"]) <= 300_000_000:
            raise ValueError(f"Row {n}: invalid 1-based position")
        row["pos1"] = int(row["pos1"])
        ref, alt = row["ref"], row["alt"]
        if any(not re.fullmatch(r"[ACGT]{1,1000}", s) for s in (ref, alt)) or ref == alt:
            raise ValueError(f"Row {n}: REF/ALT must be different A/C/G/T sequences (1–1,000 bp)")
        if len(ref) != len(alt) and not ((len(ref) == 1 or len(alt) == 1) and ref[0] == alt[0]):
            raise ValueError(f"Row {n}: use a simple, left-anchored VCF insertion/deletion; complex delins unsupported")
        variant_id = (raw.get("variant_group_id") or f"{row['gene_symbol']}_{n:02d}").strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", variant_id):
            raise ValueError(f"Row {n}: invalid variant_group_id")
        row.update(variant_group_id=variant_id, target_gene=row["gene_symbol"],
                   sequence_length=sequence_length, null_depth=null_depth, run_mode="api_full")
        rows.append(row)
    if not rows or len({r["variant_group_id"] for r in rows}) != len(rows):
        raise ValueError("Enter 1–20 rows with unique variant IDs")
    if len({tuple(r[k] for k in REQUIRED) for r in rows}) != len(rows):
        raise ValueError("Duplicate variants for the same target gene are not allowed")
    return rows


def validate_references(config):
    for name in ("fasta", "gtf", "samtools"):
        if not config.get(name) or not Path(config[name]).is_file():
            raise ValueError(f"Configure an existing {name} file first")
    if not Path(config["fasta"] + ".fai").is_file():
        raise ValueError("FASTA .fai index is required; run samtools faidx")
    if not os.access(config["samtools"], os.X_OK):
        raise ValueError("Configured samtools is not executable")


def preflight(rows, config):
    from importlib.metadata import version
    if version("alphagenome") != "0.8.0":
        raise ValueError("This analysis snapshot requires alphagenome==0.8.0; restore the pinned environment")
    validate_references(config)
    lengths = {}
    with Path(config["fasta"] + ".fai").open() as stream:
        for line in stream:
            fields = line.split("\t")
            lengths[fields[0]] = int(fields[1])
    wanted = {r["gene_symbol"] for r in rows}
    genes = {g: [] for g in wanted}
    gtf = Path(config["gtf"])
    opener = gzip.open if gtf.suffix == ".gz" else open
    with opener(gtf, "rt") as stream:
        for line in stream:
            if line.startswith("#"):
                continue
            fields = line.rstrip().split("\t")
            if len(fields) != 9 or fields[2] != "gene":
                continue
            match = re.search(r'gene_name "([^"]+)"', fields[8])
            if match and match[1].upper() in genes:
                genes[match[1].upper()].append((fields[0], int(fields[3])-1, int(fields[4])))
    checks = []
    # Same interval convention as genome.Variant.reference_interval.resize().
    from alphagenome.data import genome
    for row in rows:
        vid, chrom, pos = row["variant_group_id"], row["chrom"], row["pos1"]
        variant = genome.Variant(chromosome=chrom, position=pos,
                                reference_bases=row["ref"], alternate_bases=row["alt"])
        interval = variant.reference_interval.resize(row["sequence_length"])
        if interval.start < 0 or interval.end > lengths.get(chrom, 0):
            raise ValueError(f"{vid}: complete input window does not fit the configured chromosome")
        matches = [g for g in genes[row["gene_symbol"]] if g[0] == chrom and g[1] < interval.end and g[2] > interval.start]
        if len(matches) != 1:
            raise ValueError(f"{vid}: expected one unambiguous target gene overlapping the input window in GTF")
        region = f"{chrom}:{pos}-{pos+len(row['ref'])-1}"
        result = subprocess.run([config["samtools"], "faidx", config["fasta"], region],
                                env=child_environment(), capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError(f"{vid}: reference extraction failed")
        observed = "".join(s.strip() for s in result.stdout.splitlines() if not s.startswith(">"))
        if observed.upper() != row["ref"]:
            raise ValueError(f"{vid}: REF does not match the configured GRCh38 FASTA; no API request made")
        checks.append({"variant_group_id": vid, "reference_match": True,
                       "target_overlaps_window": True, "interval": str(interval)})
    return {"status": "passed", "checks": checks, "api_calls": 0,
            "limitations": "Local REF and annotation checks do not validate API eligibility or guarantee gene scorer coverage."}
