# CDNA4 ISA benchmark demo results (N=10)

Generated: 2026-04-22 10:15 UTC

Question IDs: Q01, Q02, Q05, Q08, Q10, Q12, Q14, Q15, Q16, Q18

## 1) Executive summary

- **N questions**: 10
- **Aggregate judged accuracy**: baseline **80.0%** vs RLM **75.0%** (Δ -5.0 pp)
- **Total latency**: baseline **299.3s** vs RLM **803.0s**
- **Total estimated tokens (in+out)**: baseline **1,802,178** vs RLM **3,288**
- **Timeouts**: baseline **0** (none) ; RLM **1** (Q15)

## 2) Breakdown tables

### By difficulty

| Difficulty | N | Baseline | RLM | Δ (RLM-Baseline) |
| --- | --- | --- | --- | --- |
| easy | 3 | 66.7% | 66.7% | +0.0 pp |
| medium | 4 | 100.0% | 100.0% | +0.0 pp |
| hard | 3 | 66.7% | 50.0% | -16.7 pp |

### By complexity (paper-aligned)

| Complexity | N | Baseline | RLM | Δ (RLM-Baseline) |
| --- | --- | --- | --- | --- |
| constant | 3 | 66.7% | 66.7% | +0.0 pp |
| linear | 5 | 90.0% | 100.0% | +10.0 pp |
| quadratic | 2 | 75.0% | 25.0% | -50.0 pp |

### By ISA section

| Section | N | Baseline | RLM | Δ (RLM-Baseline) |
| --- | --- | --- | --- | --- |
| 00-front-matter | 1 | 0.0% | 0.0% | +0.0 pp |
| 01-introduction | 1 | 100.0% | 100.0% | +0.0 pp |
| 03-kernel-state | 1 | 100.0% | 100.0% | +0.0 pp |
| 04-program-flow-control | 1 | 100.0% | 100.0% | +0.0 pp |
| 05-scalar-alu | 1 | 100.0% | 100.0% | +0.0 pp |
| 06-vector-alu | 1 | 100.0% | 100.0% | +0.0 pp |
| 07-matrix-arithmetic | 2 | 75.0% | 25.0% | -50.0 pp |
| 11-data-share | 1 | 100.0% | 100.0% | +0.0 pp |
| 08-scalar-memory | 1 | 50.0% | 100.0% | +50.0 pp |

## 3) Side-by-side samples (1 constant, 1 linear, 1 quadratic)

### Q08 (constant, easy, section=04-program-flow-control)

**Question**: What are the six S_CBRANCH_<test> conditions listed for conditional branching?

**Reference answer**: The six tests are VCCZ, VCCNZ, EXECZ, EXECNZ, SCCZ, and SCCNZ.

**Baseline answer** (score=1.0):

```text
The six `S_CBRANCH_<test>` conditions are `VCCZ`, `VCCNZ`, `EXECZ`, `EXECNZ`, `SCCZ`, and `SCCNZ`. These are the conditional branch tests listed in the Program Flow Control section for scalar branch instructions.
```

Judge rationale: The candidate answer exactly lists all six required conditional branch tests: VCCZ, VCCNZ, EXECZ, EXECNZ, SCCZ, and SCCNZ.

**RLM answer** (score=1.0):

```text
VCCZ, VCCNZ, EXECZ, EXECNZ, SCCZ, and SCCNZ.
```

Judge rationale: The candidate answer exactly matches all six required conditional branch tests: VCCZ, VCCNZ, EXECZ, EXECNZ, SCCZ, and SCCNZ.

### Q12 (linear, medium, section=06-vector-alu)

**Question**: Which VALU encoding supports up to three inputs plus modifiers, and can it use a 32-bit literal constant?

**Reference answer**: VOP3 (VOP3a/VOP3b) supports up to three inputs with ABS/NEG and output modifiers. VOP3 cannot use a 32-bit literal constant; literal constants are allowed only in 32-bit VALU encodings.

**Baseline answer** (score=1.0):

```text
The `VOP3` encoding supports up to three inputs, plus input modifiers (`NEG`, `ABS`) and output modifiers. It cannot use a 32-bit literal constant; only the 32-bit VALU encodings can use a literal constant.
```

Judge rationale: The candidate exactly matches the reference by identifying VOP3 as the three-input VALU encoding with ABS/NEG and output modifiers and correctly stating that VOP3 cannot use a 32-bit literal constant.

**RLM answer** (score=1.0):

```text
VOP3 supports up to three inputs plus input/output modifiers (with `VOP3a` as the common form and `VOP3b` for the scalar-destination variant), and no, VOP3 cannot use a 32-bit literal constant.
```

Judge rationale: The candidate correctly identifies VOP3/VOP3a/VOP3b as the three-input VALU encoding with modifiers and correctly states that VOP3 cannot use a 32-bit literal constant.

### Q15 (quadratic, hard, section=07-matrix-arithmetic)

**Question**: Compare control-field semantics across F64 MFMA, F8F6F4 MFMA, and SMFMAC for EXEC behavior and CBSZ/ABID/BLGP meaning.

**Reference answer**: F64 MFMA ignores CBSZ and ABID; BLGP[2:0] is repurposed to negate A/B/C inputs. F8F6F4 MFMA uses CBSZ to choose matrix-A format and BLGP to choose matrix-B format (broadcast behavior effectively BLGP==0), and forces EXEC to all active threads. SMFMAC also forces EXEC to all active threads; CBSZ/ABID are used only to select sparse-index subsets from SRC2 and do not control A/B broadcast.

**Baseline answer** (score=0.5):

```text
F64 MFMA, F8F6F4 MFMA, and SMFMAC all ignore EXEC and force all threads active.  
For F64 MFMA, CBSZ and ABID are ignored, and BLGP is repurposed as negate controls: BLGP[0] negates matrix A, BLGP[1] negates matrix B, and BLGP[2] negates matrix C.  
For F8F6F4 MFMA, CBSZ[2:0] selects matrix-A format and BLGP[2:0] selects matrix-B format instead of normal broadcast control; the format codes are FP8 E4M3, BF8 E5M2, FP6 E2M3, BF6 E3M2, and FP4 E2M1. ABID is only described for SCALE variants, where ABID[0]=1 is required to use scale sources and ABID[0]=0 forces scale factors to 1.0f.  
For SMFMAC, CBSZ and ABID are used only to select sparse-index data from `srcC` and do not control MFMA-style broadcasting; some 8-bit SMFMAC variants ignore CBSZ/ABID entirely, and BLGP meaning is not specified here.
```

Judge rationale: The answer captures most field-role differences correctly, but it incorrectly claims F64 MFMA also forces EXEC/all threads active and is not fully precise about the SMFMAC sparse-index operand/BLGP semantics.

**RLM answer** (score=0.0):

```text
[EMPTY]
```

Judge rationale: The candidate answer is empty, so it does not state any of the required semantics for F64 MFMA, F8F6F4 MFMA, or SMFMAC.

## 4) Honest limitations

- Baseline is intentionally weak: it only sees the first ~180k tokens (~720KB) of a ~920KB ISA text, so late-section facts may be systematically missing.
- This is a demo-scale run (N=10) and not a full 20-question evaluation; confidence intervals are wide.
- The LLM judge itself can be biased or noisy; scores are rubric-constrained but still model-mediated.
- RLM run quality is sensitive to MCP/session health; this run includes an RLM timeout on Q15.

## 5) Paper-faithfulness note

arXiv:2512.24601 §4 observation 3 suggests complexity×length degradation for naive baselines and better robustness for RLM-style decomposition.

In this demo, linear questions improved for RLM (100.0% vs 90.0%), but quadratic questions were lower (25.0% vs 75.0%), largely influenced by timeout behavior.

**Assessment**: Partial and mixed — RLM improved on linear questions but underperformed baseline on quadratic questions in this demo, so we did not reproduce §4 observation 3 end-to-end.
