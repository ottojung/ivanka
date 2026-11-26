# P1 ultradeep runtime attribution (retrospective)

Retrospective log intervals, not controlled CPU attribution. Candidate and original differed in run time and resource conditions. No new benchmark, no qualification, no original receipt or scorer changes. Log digests are present-day observed hashes, not proof of historical log immutability.

| Case | Original seconds | Candidate seconds | Assembly interval original / candidate | Four final output files byte-identical |
|---|---:|---:|---:|---|
| ultradeep-s000 | 132.63 | 177.90 | 2.03 / 2.69 | 4/4 |
| ultradeep-s001 | 141.28 | 190.37 | 1.99 / 2.79 | 4/4 |
| ultradeep-s002 | 139.86 | 186.86 | 2.02 / 2.82 | 4/4 |
| ultradeep-s003 | 138.84 | 159.85 | 2.07 / 2.27 | 4/4 |
| ultradeep-s004 | 138.51 | 169.00 | 2.39 / 2.30 | 4/4 |
| ultradeep-s005 | 137.80 | 161.44 | 2.08 / 2.32 | 4/4 |
| ultradeep-s006 | 138.54 | 608.53 | 2.02 / 8.73 | 4/4 |
| ultradeep-s007 | 131.95 | 658.75 | 2.02 / 10.27 | 4/4 |
| ultradeep-s008 | 131.25 | 768.71 | 2.01 / 11.81 | 4/4 |
| ultradeep-s009 | 143.33 | 836.23 | 1.97 / 11.82 | 4/4 |
| ultradeep-s010 | 131.52 | 232.00 | 1.96 / 4.04 | 4/4 |
| ultradeep-s011 | 132.67 | 238.60 | 2.02 / 3.56 | 4/4 |
| ultradeep-s012 | 134.63 | 301.97 | 1.94 / 6.32 | 4/4 |
| ultradeep-s013 | 138.46 | 292.14 | 2.09 / 3.51 | 4/4 |
| ultradeep-s014 | 141.20 | 256.66 | 2.03 / 3.65 | 4/4 |
| ultradeep-s015 | 141.03 | 289.99 | 2.11 / 4.06 | 4/4 |

For s009, the native assembly interval is only about 12 s of the 836 s candidate runtime. The pre-assembly fastq_g2p stage and shared post-assembly stages also slowed, indicating that optimizing native assembly alone cannot explain or recover the whole runtime gap. A matched-condition diagnostic is required. The companion JSON preserves observed log digests and stage intervals.
