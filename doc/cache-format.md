# The lightspeed cache format

This is the contract between the Python and Haskell implementations. A cache
directory written by one must be read, extended and shared by the other, while
both are running. It describes **schema version 3**, what the Python package
writes as of `lightspeed-series` 0.0.1.

Anything here that the Python code does differently is a bug in one or the
other; fix the code or this document, never leave them apart. A change to what
is written bumps `schema_version` (section 3.1) and is made in both
implementations together.

The words *must*, *must not* and *should* are used in their usual
specification sense.

## 1. What is cached

A **series** is a 1-D run of `N` samples read from an HDF5 file (the
**source**):

- **y**: the values. A 1-D dataset, or one column of a 2-D (rows x columns)
  dataset. Any integer or floating type.
- **x** (optional): for an *irregular* series, a coordinate per sample, from a
  1-D dataset or a column of a 2-D one, of the same length. It must be
  non-decreasing; a build that finds a sample less than the one before it
  fails. A *uniform* series has no x dataset: sample `i` is at coordinate `i`.
- **status** (optional): an integer code per sample, of the same length, with
  a **status map** saying what each code means (section 5).

The cache never stores the axis mapping (`x = x0 + coord * dx`): it holds
coordinates as the file has them (or sample indexes), so the mapping can
change without a rebuild.

A cache holds a **pyramid** of levels. Level 0 has one bucket per
`chunk_size` consecutive samples; each level above has one bucket per two of
the level below. Every bucket records the min and max of the values it covers,
which kinds of missing sample it covers, and, for an irregular series, the min
and max coordinate it covers.

## 2. The cache directory

One directory holds the caches of any number of series, and is shared by any
number of processes, in either language, at once.

```
<cache dir>/
  <content hash>.h5          one cache file per series (section 3)
  memo.json                  source -> content hash (section 6)
  locks/
    memo.lock                taken to rewrite memo.json
    build-<16 hex>.lock      taken to build one series' cache (section 7)
  cache-*.h5.tmp             a cache file being written (section 3.4)
  memo-*.json.tmp            memo.json being written
```

Where the directory is, when the caller does not say, is up to each
implementation; Python's default is in its README. Two implementations share
a cache only if they are pointed at the same directory.

## 3. The cache file

`<content hash>.h5`, an HDF5 file. The name is the series' content hash
(section 4), lower-case hex, and `.h5`.

### 3.1 Root attributes

| Attribute | HDF5 type | Value |
|---|---|---|
| `schema_version` | 64-bit signed integer | `3` |
| `content_hash` | variable-length string | the content hash; must equal the file name's stem |
| `source_length` | 64-bit signed integer | `N`, the number of samples |
| `chunk_size` | 64-bit signed integer | samples per level-0 bucket; a power of two |
| `irregular_x` | 8-bit unsigned integer | `1` for an irregular series, `0` for a uniform one |
| `dtype` | variable-length string | the y dataset's element type, as a numpy dtype string (below) |
| `x_dtype` | variable-length string | the x dataset's element type, likewise; present only when `irregular_x` is 1 |
| `n_levels` | 64-bit signed integer | the number of levels, at least 1 |
| `source_path_hint` | variable-length string | the source file's path when the cache was built. Informative only |
| `dataset_path_hint` | variable-length string | the cache selector (section 6.1). Informative only |
| `built_at` | variable-length string | when the cache was built, ISO 8601 with a UTC offset (`2026-11-15T21:24:43.622841+00:00`). Informative only |

Strings are UTF-8. A reader must not depend on the three informative
attributes.

The dtype strings are numpy's `str(dtype)`: a native little-endian type is
its name (`float64`, `float32`, `int64`, `int32`, `int16`, `int8`, `uint64`,
`uint32`, `uint16`, `uint8`), and a big-endian one is its type code
(`>f8`, `>f4`, `>i8`, `>i4`, `>i2`, `>u8`, `>u4`, `>u2`). They describe the
source, not the cache file's own datasets, whose types are fixed below.

### 3.2 Levels

For each level `L` from `0` to `n_levels - 1`, a group `/levels/<L>`, holding
1-D datasets of one common length, the level's bucket count `B_L`:

| Dataset | Element type | Present |
|---|---|---|
| `y_min` | 64-bit IEEE float | always |
| `y_max` | 64-bit IEEE float | always |
| `missing` | 32-bit unsigned integer | always |
| `x_min` | the x dataset's element type (as `x_dtype`) | irregular series only |
| `x_max` | the x dataset's element type (as `x_dtype`) | irregular series only |

Byte order is the writer's (HDF5 records it, and readers convert). Each
dataset is chunked, with a chunk shape the writer chooses, and compressed
with the **LZF** filter (HDF5 filter id 32000) - see section 9, issue 1.

A reader must treat the file as corrupt (and so rebuild it, section 8) if the
`content_hash` attribute does not match the file name, if `schema_version` is
not one it reads, or if any level is missing `y_min`, `y_max` or `missing`, or
for an irregular series `x_min` or `x_max`.

### 3.3 Bucket contents

**Level 0.** Bucket `b` covers samples `b * chunk_size` up to (not including)
`min((b + 1) * chunk_size, N)`; the last bucket is shorter when `N` is not a
multiple of `chunk_size`. So `B_0 = ceil(N / chunk_size)`, and `0` for an
empty series.

For each bucket, over the samples it covers, with each sample's *value* and
*kind* as section 5 gives them:

- `y_min`, `y_max`: the least and greatest value as a 64-bit float, ignoring
  samples whose value is NaN. A bucket with no non-NaN value has NaN for both.
- `missing`: the bitwise OR of the samples' kind bits (section 5).
- `x_min`, `x_max` (irregular): the least and greatest coordinate, in the x
  dataset's own type. Since x is sorted, the first and last.

**Levels above 0.** Level `L + 1` pairs the buckets of level `L` from the
start: bucket `j` combines buckets `2j` and `2j + 1` of level `L`. When `B_L`
is odd, the last bucket of level `L` is carried up unchanged as the last
bucket of level `L + 1`. Combining:

- `y_min` is the lesser of the two ignoring NaN (`fmin`): NaN only if both
  are NaN. `y_max` likewise with the greater (`fmax`).
- `missing` is the bitwise OR.
- `x_min` is the lesser, `x_max` the greater.

So bucket `j` of level `L` covers samples from `j * chunk_size * 2^L` (and to
the end of the series for the last bucket).

**How many levels.** Level 0 is always present, even when empty. A level
`L + 1` is made from level `L` while `B_L > 1` and `B_L > 8`; the first level
with 8 buckets or fewer is the top. (8 is `MIN_LEVEL_BUCKETS`.)

### 3.4 Writing

A cache file is written to a temporary file in the cache directory, named
`cache-<random>.h5.tmp`, closed, and then renamed over `<content hash>.h5` in
one atomic step. A reader therefore sees a whole file or none. A writer must
remove its temporary file if it fails.

If the rename fails because another process has the destination open (Windows
refuses to replace an open file) and the destination exists, the writer
removes its temporary file and uses the existing one: it has the same content
hash, so the same contents.

## 4. The content hash

The cache file is named by a hash of the data, so two sources with the same
samples share one cache, and a source that changes gets a new one.

It is BLAKE2b with a 16-byte digest (no key, no salt, no personalisation),
written as 32 lower-case hex digits. The bytes hashed, in order, are:

1. If the series has a status array: the ASCII bytes of the status map's
   fingerprint (section 5.2), 16 hex characters.
2. The samples, in blocks of `S` samples (the last block shorter): for each
   block in turn, the y values of that block, then (irregular) its x values,
   then (with status) its status codes.

Each array's bytes are its elements as they are stored in the source -
the dataset's own element type and byte order, packed, with no conversion.
A column of a 2-D dataset is that column's elements only.

`S` is `2^20` (1,048,576) samples when `chunk_size <= 2^20`, and `chunk_size`
otherwise. Because y, x and status are interleaved block by block, the hash
depends on `S`: an implementation must use the same blocks to reach the same
hash. (See section 9, issue 4.)

## 5. Sample kinds and the missing mask

Each sample has a **kind**, which says whether it is drawn:

- **valid**: drawn at its value.
- **skip**: not a sample at all (a sensor read every tenth tick has nine
  skipped ticks in ten). Not drawn; the line joins across it, unmarked.
- **missing, of some kind**: a sample was expected and there is none, or it
  is NaN. Not drawn; the line breaks there, and the gap can be marked.

Each kind of missing is one bit of the 32-bit `missing` mask:

| Bit | Kind |
|---|---|
| 0 | NaN: a NaN value whose status is valid, or any NaN in a series with no status |
| 1 | unknown: a status code the status map does not name |
| 2-31 | the codes the status map says mean *absent*, in the order they are declared: the first such code is bit 2, the next bit 3 |

A valid or skipped sample contributes no bits.

### 5.1 Values

With no status array, a sample's value is y converted to a 64-bit float, and
its kind is NaN-missing if that value is NaN (only a float type can be) and
valid otherwise.

With a status array, a sample's kind is its code's (an unnamed code is
unknown-missing; a valid code over a NaN value is NaN-missing), and its value
is y converted to a 64-bit float where the kind is valid and NaN otherwise.
So a skipped or missing sample never affects `y_min` or `y_max`.

### 5.2 The status map

Declared as a list of `(code, meaning)` pairs, meaning one of `valid`,
`skip`, `absent`. No code may be declared twice, and at most 30 may be
`absent`.

Each code gets a number: `-1` for valid, `-2` for skip, and its bit for
absent (2 for the first absent code declared, and so on). The
**fingerprint** names the whole map:

1. Sort the codes in ascending numeric order.
2. Write each as `<code>:<number>` in decimal (`0:-1`, `2:2`, `-5:-2`) and
   join them with `,`.
3. SHA-256 of that ASCII text; the first 16 lower-case hex digits.

So the map `[(0, valid), (1, skip), (2, absent)]` is `0:-1,1:-2,2:2`.

## 6. The memo

`memo.json` maps each source series to the content hash of its cache, so an
unchanged source is found without being read and hashed again.

```json
{
  "version": 1,
  "entries": {
    "<source path>::<cache selector>": {
      "mtime_ns": 1794777883594777977,
      "size": 262048,
      "chunk_size": 1024,
      "content_hash": "643d27c4573931199dcc58547ae84fa2",
      "irregular_x": true
    }
  }
}
```

- `<source path>` is the source file's absolute path with every symbolic link
  resolved.
- `mtime_ns` is the source file's modification time in integer nanoseconds
  since the Unix epoch, and `size` its size in bytes, as the file system
  reported them when the cache was built.

An entry is used only if `mtime_ns`, `size` and `chunk_size` all equal the
source's as it is now and the chunk size asked for, and the cache file it
names exists and opens soundly (section 3.2). Otherwise the series is built
again.

A reader must ignore an unreadable or malformed `memo.json` (treat it as
empty), and skip any entry it cannot parse, rather than fail.

### 6.1 The cache selector

Says which arrays of the source the cache is of:

- `<y>` for a series with no status, where `<y>` is the y dataset's path, or
  `<path>[<column>]` for a column of a 2-D dataset: `/y`, `/values[3]`.
- `<y>|status=<status>@<fingerprint>` for one with a status array, `<status>`
  written the same way: `/y|status=/st@78bf0d8a44ab2483`.

The x dataset is not part of it.

### 6.2 Writing the memo

The memo is read, changed and written back whole, so a writer must hold
`locks/memo.lock` (section 7) from before it reads until after it writes. It
writes a temporary `memo-<random>.json.tmp` in the cache directory and
renames it over `memo.json` atomically. A writer must keep the entries it
does not change, including ones it does not understand.

## 7. Locks

Each lock is an exclusive lock on a file under `locks/`, created if it is
not there, of the kind Python's `filelock` package takes: `flock(fd,
LOCK_EX)` on POSIX, and a C-runtime byte-range lock (`msvcrt.locking`) on
Windows. An implementation must take the same kind, so the two exclude each
other; on Windows that needs checking against `filelock` itself. The lock
files are never removed.

- `memo.lock`: held while rewriting `memo.json`.
- `build-<16 hex>.lock`: held while building one series' cache. The hex is
  the first 16 lower-case hex digits of SHA-256 of
  `<source path>::<cache selector>` as UTF-8 (the same text as the memo key).

A process that needs a cache which is not in the memo takes the build lock,
then looks in the memo again - another process may have just built it - and
builds only if it is still not there. A process that finds the lock held
waits for it.

## 8. Reading (informative)

Not part of the file format, but what each implementation does with it, so
that both draw a series the same way.

To show coordinates `[c0, c1]` with about `T` buckets:

1. Find the sample range `[i0, i1)` that covers it. Uniform: `i0 = floor(c0)`,
   `i1 = ceil(c1) + 1`. Irregular: binary-search level 0's `x_max` for `c0`
   and `x_min` for `c1` to find the chunks, then the raw x of just the first
   and last chunk for the exact samples. Clamp to `[0, N)`.
2. With `w = (i1 - i0) / T`: if `w >= chunk_size`, read level
   `L = min(floor(log2(w)) - log2(chunk_size), n_levels - 1)`, buckets
   `floor(i0 / (chunk_size * 2^L))` up to `ceil(i1 / (chunk_size * 2^L))`.
   Otherwise read the source itself: the raw samples if there are at most `T`,
   or else buckets of `ceil((i1 - i0) / T)` samples reduced as level 0 is.
3. Place each bucket at the midpoint of its `x_min` and `x_max` (irregular),
   or at `(bucket index + 0.5) * bucket width` (uniform).
4. Leave out every bucket whose `y_min` is NaN and whose `missing` is 0: it
   holds only skipped samples, and the line joins across it.

A cache file is only ever replaced whole (section 3.4), so a reader may keep
one open while another process writes a new cache for the same source.

## 9. Open issues

Things in schema version 3 that work for Python alone and get in the way of a
second implementation. Each is a candidate for schema version 4.

1. **LZF compression.** LZF is h5py's own filter, not part of the HDF5
   library: a reader in any other language needs the LZF filter plugin
   installed to read a cache at all. DEFLATE (gzip, filter id 1), with the
   shuffle filter, is built into every HDF5 and would remove the dependency,
   at some cost in build time.
2. **Numpy dtype strings.** `dtype` and `x_dtype` are numpy's spellings, so
   other readers need a table to parse them (section 3.1). Plainer would be
   to drop them and read the type from the HDF5 datasets themselves, or to
   spell them out (`float`, `little`, `64`).
3. **`chunk_size` is not in the content hash**, so a series built at two chunk
   sizes gets two caches with the same file name, each replacing the other.
   The memo records the chunk size, so the result is a rebuild rather than a
   wrong answer, but the two would keep displacing each other. Including the
   chunk size in the hash (or the file name) would fix it.
4. **The hash depends on the block size** used to read the source (section
   4). Hashing each array whole, one after the other, would make it a property
   of the data alone, at the cost of reading the source three times, or
   hashing three streams at once.
5. **The element type is not in the content hash.** Two sources whose bytes
   are the same but whose types differ (`int32` and `float32`, or the two byte
   orders) hash the same. Unlikely in practice; hashing each array's type and
   length first would close it.
6. **Integers wider than 53 bits** lose precision in `y_min` and `y_max`,
   which are 64-bit floats whatever the source type.
7. **Rolling series** (planned): live data appended to a source while it is
   drawn. Content-addressed, whole-file caches assume a source that does not
   change; extending a pyramid as samples arrive will need a cache that can be
   appended to, and the memo and file naming will need to allow for it.
