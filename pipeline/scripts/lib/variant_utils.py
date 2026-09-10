"""Variant normalization helpers.

Pipeline contract:
- Inputs are 0-based half-open BED intervals (`start0`, `end0`) describing the
  16-bp 5xCCG motif on hg38.
- `human_aligned` is the forward-orientation motif (`CCGCCGCCGCCGCCCG`).
- `chimp_aligned` may be in motif/gene orientation. If the motif's hg38 forward
  sequence equals `reverse_complement(human_aligned)`, we treat the alignment
  as reverse-complement of the genomic forward strand and flip the alleles
  before turning them into VCF-style records.

This module produces VCF-style anchored alleles (1-based POS, REF/ALT with a
single anchor base) that are then left-normalized against hg38.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .fasta import FastaExtractor, reverse_complement


# ---------------------------------------------------------------------------
# Alignment-to-edit parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MotifEdit:
    """One edit derived from a motif-frame alignment.

    Positions are 0-based offsets within the 16-bp motif. The edit is described
    in motif orientation (NOT yet in genomic forward orientation).
    """

    kind: str          # "del" or "snv"
    motif_offset: int  # 0-based offset in the 16-bp motif of the first edited base
    ref_motif: str     # uppercase REF bases in motif orientation
    alt_motif: str     # uppercase ALT bases in motif orientation ("" for deletion)


def parse_alignment(human: str, chimp: str) -> List[MotifEdit]:
    """Parse a gapped 2-row alignment into discrete edits (deletions / SNVs).

    Insertions in chimp relative to human are not expected in this dataset; if
    encountered, they are emitted as "ins" edits and the caller must handle them.
    """
    if len(human) != len(chimp):
        raise ValueError(
            f"Alignment length mismatch: human={len(human)} chimp={len(chimp)}"
        )

    edits: List[MotifEdit] = []
    i = 0
    n = len(human)
    while i < n:
        h = human[i]
        c = chimp[i]
        if h == "-" and c == "-":
            i += 1
            continue
        if c == "-":
            # Deletion in chimp relative to human; collect run.
            start = i
            ref_run = []
            while i < n and chimp[i] == "-" and human[i] != "-":
                ref_run.append(human[i])
                i += 1
            edits.append(
                MotifEdit(
                    kind="del",
                    motif_offset=start,
                    ref_motif="".join(ref_run).upper(),
                    alt_motif="",
                )
            )
            continue
        if h == "-":
            # Insertion in chimp relative to human; not expected here.
            start = i
            alt_run = []
            while i < n and human[i] == "-" and chimp[i] != "-":
                alt_run.append(chimp[i])
                i += 1
            edits.append(
                MotifEdit(
                    kind="ins",
                    motif_offset=start,
                    ref_motif="",
                    alt_motif="".join(alt_run).upper(),
                )
            )
            continue
        # Both real bases.
        if h.upper() != c.upper():
            edits.append(
                MotifEdit(
                    kind="snv",
                    motif_offset=i,
                    ref_motif=h.upper(),
                    alt_motif=c.upper(),
                )
            )
        i += 1
    return edits


# ---------------------------------------------------------------------------
# Motif-frame -> genomic forward orientation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MotifPlacement:
    """How a motif sits on hg38 forward strand."""
    chrom: str
    motif_start0: int            # 0-based start on hg38 forward
    motif_end0: int              # 0-based half-open end on hg38 forward
    forward_seq: str             # hg38 forward sequence of the motif (16 bp)
    motif_is_reverse_complemented: bool


def detect_orientation(
    extractor: FastaExtractor,
    chrom: str,
    start0: int,
    end0: int,
    expected_motif: str,
) -> MotifPlacement:
    """Compare hg38 forward sequence to `expected_motif`.

    Returns whether the alignment-frame motif equals the forward sequence
    directly (motif_is_reverse_complemented=False) or its reverse complement
    (motif_is_reverse_complemented=True). Raises if neither matches.
    """
    forward = extractor.fetch_bed(chrom, start0, end0)
    em = expected_motif.upper()
    if forward == em:
        rc = False
    elif reverse_complement(forward) == em:
        rc = True
    else:
        raise ValueError(
            f"Motif mismatch at {chrom}:{start0}-{end0}.\n"
            f"  hg38 forward : {forward}\n"
            f"  expected motif: {em}\n"
            f"  RC(hg38 fwd) : {reverse_complement(forward)}\n"
        )
    return MotifPlacement(
        chrom=chrom,
        motif_start0=start0,
        motif_end0=end0,
        forward_seq=forward,
        motif_is_reverse_complemented=rc,
    )


# ---------------------------------------------------------------------------
# Build VCF-style anchored variants on hg38 forward
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VcfVariant:
    """1-based VCF representation on hg38 forward."""
    chrom: str
    pos1: int
    ref: str
    alt: str

    @property
    def variant_id(self) -> str:
        return f"{self.chrom}:{self.pos1}:{self.ref}>{self.alt}"


def _edits_to_forward(
    edits: List[MotifEdit],
    placement: MotifPlacement,
) -> List[MotifEdit]:
    """Map motif-frame edits onto hg38 forward orientation.

    If the motif is reverse-complemented relative to hg38 forward, each edit's
    bases must be reverse-complemented and its offset flipped within the motif.
    """
    if not placement.motif_is_reverse_complemented:
        return edits
    motif_len = placement.motif_end0 - placement.motif_start0
    forward_edits: List[MotifEdit] = []
    for e in edits:
        if e.kind in ("del", "snv"):
            ref_len = len(e.ref_motif)
            fwd_offset = motif_len - e.motif_offset - ref_len
            forward_edits.append(
                MotifEdit(
                    kind=e.kind,
                    motif_offset=fwd_offset,
                    ref_motif=reverse_complement(e.ref_motif),
                    alt_motif=reverse_complement(e.alt_motif) if e.alt_motif else "",
                )
            )
        else:
            raise NotImplementedError(
                f"RC mapping for edit kind {e.kind!r} is not implemented "
                "(no insertion expected in this dataset)."
            )
    return forward_edits


def edits_to_vcf(
    edits: List[MotifEdit],
    placement: MotifPlacement,
    extractor: FastaExtractor,
) -> List[VcfVariant]:
    """Convert per-edit info into VCF-style anchored alleles on hg38 forward.

    SNVs are emitted as single-base records (no anchor needed).
    Deletions use a left-anchor base so REF and ALT both start with the anchor,
    which is the canonical VCF convention and friendly to AlphaGenome's batch
    TSV input.
    """
    forward_edits = _edits_to_forward(edits, placement)
    vcfs: List[VcfVariant] = []
    for e in forward_edits:
        if e.kind == "snv":
            pos1 = placement.motif_start0 + e.motif_offset + 1
            ref_in_hg38 = extractor.fetch(placement.chrom, pos1, pos1)
            if ref_in_hg38 != e.ref_motif:
                raise ValueError(
                    f"SNV REF mismatch at {placement.chrom}:{pos1}: "
                    f"hg38={ref_in_hg38} vs alignment={e.ref_motif}"
                )
            vcfs.append(VcfVariant(placement.chrom, pos1, ref_in_hg38, e.alt_motif))
        elif e.kind == "del":
            del_pos1 = placement.motif_start0 + e.motif_offset + 1
            anchor_pos1 = del_pos1 - 1
            if anchor_pos1 < 1:
                raise ValueError(
                    f"Left anchor falls before the chromosome at "
                    f"{placement.chrom}:{del_pos1} — cannot anchor."
                )
            anchor = extractor.fetch(placement.chrom, anchor_pos1, anchor_pos1)
            ref_in_hg38 = extractor.fetch(
                placement.chrom, del_pos1, del_pos1 + len(e.ref_motif) - 1
            )
            if ref_in_hg38 != e.ref_motif:
                raise ValueError(
                    f"DEL REF mismatch at {placement.chrom}:{del_pos1}-: "
                    f"hg38={ref_in_hg38} vs alignment={e.ref_motif}"
                )
            vcfs.append(
                VcfVariant(
                    chrom=placement.chrom,
                    pos1=anchor_pos1,
                    ref=anchor + ref_in_hg38,
                    alt=anchor,
                )
            )
        else:
            raise NotImplementedError(f"edit kind {e.kind!r} not supported")
    return vcfs


# ---------------------------------------------------------------------------
# Left-normalization (vt-style) for indels in repeat regions
# ---------------------------------------------------------------------------


def left_normalize(
    variant: VcfVariant,
    extractor: FastaExtractor,
    max_shift: int = 100,
) -> VcfVariant:
    """vt-norm-style left alignment in repeat context.

    Algorithm (from the vt / bcftools norm specification):
      1. While REF and ALT end with the same base and len(REF) > 1 and len(ALT) > 1:
         trim the trailing base.
      2. While the leftmost base of REF and ALT are the same and we can pad to
         the left without falling off the chromosome:
           - prepend the preceding genomic base to both REF and ALT
           - decrement POS
      3. Trim shared leading bases as long as both REF and ALT have length > 1.

    This produces the canonical left-aligned representation expected by VCF
    consumers. SNVs are returned unchanged.
    """
    if len(variant.ref) == 1 and len(variant.alt) == 1:
        return variant

    chrom = variant.chrom
    pos = variant.pos1
    ref = variant.ref
    alt = variant.alt

    # Step 1: trim trailing matches.
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref = ref[:-1]
        alt = alt[:-1]

    # Step 2: extend to the left while leading bases match.
    shifted = 0
    while ref and alt and ref[0] == alt[0]:
        if pos <= 1 or shifted >= max_shift:
            break
        prev = extractor.fetch(chrom, pos - 1, pos - 1)
        ref = prev + ref
        alt = prev + alt
        pos -= 1
        shifted += 1
        # After prepending we may have created a new trailing match. Trim again.
        while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
            ref = ref[:-1]
            alt = alt[:-1]

    # Step 3: trim shared leading bases (keeping anchored representation).
    while (
        len(ref) > 1
        and len(alt) > 1
        and ref[0] == alt[0]
    ):
        ref = ref[1:]
        alt = alt[1:]
        pos += 1

    return VcfVariant(chrom=chrom, pos1=pos, ref=ref, alt=alt)
