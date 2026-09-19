# vision: results

model jev-1.13.0, 2300 calls ok, 0 errors, input 1,656,393 + output 150,645 tokens, 630s.

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
