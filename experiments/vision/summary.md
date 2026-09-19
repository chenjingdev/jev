# vision: results

model jev-1.13.0, 2900 calls ok, 0 errors, input 2,131,638 + output 217,452 tokens, 795s.

## encode: colour grids, by spelling

acc = share correct; chance = 1/palette averaged over the rows; collapse = share of calls that picked the single most-picked option; gold p = mean probability on the right answer.

### question `pos`

| format | n | acc | chance | collapse | top pick | gold p | in tok | ms |
|---|---|---|---|---|---|---|---|---|
| names | 100 | 0.98 | 0.19 | 0.23 | red | 0.96 | 627 | 270 |
| rgb | 100 | 1.00 | 0.19 | 0.22 | red | 0.98 | 978 | 266 |
| hex | 100 | 1.00 | 0.19 | 0.22 | red | 0.97 | 791 | 260 |
| ppm | 100 | 0.40 | 0.19 | 0.20 | green | 0.32 | 968 | 258 |
| b64rgb | 100 | 0.22 | 0.19 | 0.46 | black | 0.19 | 685 | 259 |
| b64rgb_off | 100 | 0.21 | 0.19 | 0.45 | red | 0.19 | 684 | 257 |
| b64bmp | 100 | 0.22 | 0.19 | 0.49 | red | 0.19 | 715 | 256 |
| b64png0 | 100 | 0.19 | 0.19 | 0.55 | red | 0.19 | 723 | 256 |
| b64png | 100 | 0.21 | 0.19 | 0.47 | red | 0.19 | 666 | 264 |

### question `mode`

| format | n | acc | chance | collapse | top pick | gold p | in tok | ms |
|---|---|---|---|---|---|---|---|---|
| names | 100 | 0.87 | 0.19 | 0.33 | green | 0.75 | 611 | 262 |
| rgb | 100 | 0.82 | 0.19 | 0.29 | green | 0.69 | 962 | 270 |
| hex | 100 | 0.79 | 0.19 | 0.30 | green | 0.68 | 775 | 256 |
| ppm | 100 | 0.42 | 0.19 | 0.25 | white | 0.31 | 952 | 256 |
| b64rgb | 100 | 0.15 | 0.19 | 0.50 | red | 0.18 | 669 | 263 |
| b64rgb_off | 100 | 0.17 | 0.19 | 0.50 | red | 0.19 | 668 | 267 |
| b64bmp | 100 | 0.16 | 0.19 | 0.50 | red | 0.19 | 699 | 259 |
| b64png0 | 100 | 0.13 | 0.19 | 0.50 | red | 0.17 | 707 | 255 |
| b64png | 100 | 0.13 | 0.19 | 0.50 | red | 0.17 | 650 | 261 |

### by grid size and palette (question `pos`)

| format | 4x4 / 4 colours | 4x4 / 8 colours | 8x8 / 4 colours | 8x8 / 8 colours |
|---|---|---|---|---|
| names | 1.00 | 1.00 | 0.96 | 0.96 |
| rgb | 1.00 | 1.00 | 1.00 | 1.00 |
| hex | 1.00 | 1.00 | 1.00 | 1.00 |
| ppm | 0.48 | 0.56 | 0.28 | 0.28 |
| b64rgb | 0.32 | 0.20 | 0.24 | 0.12 |
| b64rgb_off | 0.36 | 0.12 | 0.24 | 0.12 |
| b64bmp | 0.32 | 0.12 | 0.28 | 0.16 |
| b64png0 | 0.16 | 0.16 | 0.28 | 0.16 |
| b64png | 0.28 | 0.16 | 0.28 | 0.12 |

### by grid size and palette (question `mode`)

| format | 4x4 / 4 colours | 4x4 / 8 colours | 8x8 / 4 colours | 8x8 / 8 colours |
|---|---|---|---|---|
| names | 0.96 | 0.92 | 0.84 | 0.76 |
| rgb | 0.92 | 0.92 | 0.84 | 0.60 |
| hex | 0.80 | 0.92 | 0.76 | 0.68 |
| ppm | 0.64 | 0.36 | 0.40 | 0.28 |
| b64rgb | 0.16 | 0.12 | 0.12 | 0.20 |
| b64rgb_off | 0.16 | 0.20 | 0.12 | 0.20 |
| b64bmp | 0.16 | 0.16 | 0.12 | 0.20 |
| b64png0 | 0.16 | 0.16 | 0.12 | 0.08 |
| b64png | 0.16 | 0.16 | 0.12 | 0.08 |

### positional accuracy by row, readable spellings, 8x8

| format | row 1 | row 2 | row 3 | row 4 | row 5 | row 6 | row 7 | row 8 |
|---|---|---|---|---|---|---|---|---|
| names | 1.00 (8) | 1.00 (9) | 1.00 (6) | 1.00 (4) | 1.00 (4) | 1.00 (9) | 0.86 (7) | 0.67 (3) |
| rgb | 1.00 (8) | 1.00 (9) | 1.00 (6) | 1.00 (4) | 1.00 (4) | 1.00 (9) | 1.00 (7) | 1.00 (3) |
| hex | 1.00 (8) | 1.00 (9) | 1.00 (6) | 1.00 (4) | 1.00 (4) | 1.00 (9) | 1.00 (7) | 1.00 (3) |
| ppm | 0.00 (8) | 0.44 (9) | 0.17 (6) | 0.25 (4) | 0.25 (4) | 0.33 (9) | 0.43 (7) | 0.33 (3) |

## grid: screens as coarse label grids, by shape

`pos` = label of one named cell (chance 1/6); `find_row` / `find_col` = which row / column holds the unique `input` cell (chance 1/rows, 1/cols).

### spelling `words`

| shape | pos | find_row | find_col | in tok |
|---|---|---|---|---|
| 8x8 | 1.00 (chance 0.17, gold p 0.98) | 1.00 (chance 0.12, gold p 1.00) | 1.00 (chance 0.12, gold p 0.97) | 559 |
| 16x9 | 0.80 (chance 0.17, gold p 0.70) | 1.00 (chance 0.11, gold p 1.00) | 0.80 (chance 0.06, gold p 0.67) | 689 |
| 24x14 | 0.68 (chance 0.17, gold p 0.56) | 1.00 (chance 0.07, gold p 0.99) | 0.56 (chance 0.04, gold p 0.48) | 957 |
| 32x18 | 0.64 (chance 0.17, gold p 0.43) | 0.88 (chance 0.06, gold p 0.88) | 0.40 (chance 0.03, gold p 0.42) | 1265 |

### spelling `letters`

| shape | pos | find_row | find_col | in tok |
|---|---|---|---|---|
| 8x8 | 0.84 (chance 0.17, gold p 0.73) | 1.00 (chance 0.12, gold p 0.99) | 0.88 (chance 0.12, gold p 0.77) | 526 |
| 16x9 | 0.40 (chance 0.17, gold p 0.40) | 1.00 (chance 0.11, gold p 1.00) | 0.44 (chance 0.06, gold p 0.37) | 612 |
| 24x14 | 0.28 (chance 0.17, gold p 0.32) | 1.00 (chance 0.07, gold p 0.96) | 0.52 (chance 0.04, gold p 0.31) | 774 |
| 32x18 | 0.28 (chance 0.17, gold p 0.32) | 1.00 (chance 0.06, gold p 0.98) | 0.32 (chance 0.03, gold p 0.20) | 954 |

### find_row / find_col: how far off, spelling `words`

| shape | find_row | find_col |
|---|---|---|
| 8x8 | exact 25, off by 1: 0, off by 2+: 0 | exact 25, off by 1: 0, off by 2+: 0 |
| 16x9 | exact 25, off by 1: 0, off by 2+: 0 | exact 20, off by 1: 3, off by 2+: 2 |
| 24x14 | exact 25, off by 1: 0, off by 2+: 0 | exact 14, off by 1: 7, off by 2+: 4 |
| 32x18 | exact 22, off by 1: 3, off by 2+: 0 | exact 10, off by 1: 10, off by 2+: 5 |

## pixel: MNIST digits 14x14, by spelling

| format | n | acc | chance | collapse | top pick | gold p | in tok | ms |
|---|---|---|---|---|---|---|---|---|
| binary | 100 | 0.36 | 0.10 | 0.48 | 9 | 0.18 | 556 | 252 |
| density | 100 | 0.31 | 0.10 | 0.32 | 7 | 0.14 | 595 | 257 |
| braille | 100 | 0.16 | 0.10 | 0.94 | 7 | 0.12 | 605 | 249 |
| coords | 100 | 0.22 | 0.10 | 0.45 | 8 | 0.14 | 674 | 252 |
| runlength | 100 | 0.11 | 0.10 | 0.76 | 0 | 0.12 | 606 | 251 |

### per digit (rows: spelling, cols: true digit, cell: correct/10)

| format | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| binary | 3 | 10 | 1 | 0 | 1 | 0 | 0 | 7 | 8 | 6 |
| density | 5 | 8 | 1 | 0 | 0 | 0 | 0 | 7 | 6 | 4 |
| braille | 0 | 5 | 1 | 0 | 0 | 0 | 0 | 10 | 0 | 0 |
| coords | 1 | 4 | 6 | 0 | 0 | 0 | 0 | 0 | 9 | 2 |
| runlength | 10 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 0 |

### confusion, best spelling (rows: true, cols: picked)

spelling `binary`

| true \ picked | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 3 |  |  |  |  |  |  |  | 3 | 4 |
| 1 |  | 10 |  |  |  |  |  |  |  |  |
| 2 |  |  | 1 |  |  |  |  | 1 |  | 8 |
| 3 |  |  | 3 |  |  |  |  | 1 | 4 | 2 |
| 4 |  |  |  |  | 1 |  |  |  |  | 9 |
| 5 |  |  | 1 |  |  |  |  | 1 | 1 | 7 |
| 6 |  |  | 1 |  |  |  |  | 1 | 1 | 7 |
| 7 |  |  |  |  |  |  |  | 7 |  | 3 |
| 8 |  |  |  |  |  |  |  |  | 8 | 2 |
| 9 |  |  |  |  |  |  |  | 3 | 1 | 6 |
