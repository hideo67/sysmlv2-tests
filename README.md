# test suite for sysml MDKs

This project provides a common test suite to be run against various SysML v2 MDK
APIs. It provides a set of matrices to define the combination of conditions to
be tested. A set of model files are prepared, and then a test suite is provided
for each of the APIs to be tested.

The following APIs will be target of the test:

- https://github.com/Systems-Modeling/SysML-v2-Pilot-Implementation
- https://github.com/Open-MBEE/OpenSysML
- https://github.com/Open-MBEE/sysml-toolkit

The test case matrices assigns a common ID to the test cases, and each test test
suite uses the common ID.

The project has the following directory structure:

- test-suite
  - data
  - test-sysml-v2-pilot-implementation-java
  - test-opensysml-go
  - test-opensysml-py
  - test-opensysml-ts (planned)
  - test-opensysml-java (planned)
  - test-opensysml-rs (planned)
  - test-sysml-toolkit-rs
  - results (created by a test run, not tracked by git)
- SysMLv2-Pilot-Implementation
- OpenSysML
- sysml-toolkit

data holds the matrix definitions and the test data.
test-* directories contains the test suites.
siblings of the test-suite are cloned project repositories of the MDKs to be tested.

# Building and running

The MDKs are cloned next to `test-suite` and built from source. The test
suites use those local builds, never released packages. The steps below were
used on Linux (Ubuntu under WSL2).

## Prerequisites

| Tool | Version | Needed for |
|---|---|---|
| git | any recent | cloning |
| Python | 3.10 or later | the OpenSysML Python suite, the matrix generators and report scripts |
| [uv](https://docs.astral.sh/uv/) | any recent | the Python suite's virtual environment |
| Go | 1.26 or later (OpenSysML pins toolchain go1.27.3) | building OpenSysML, the OpenSysML Go suite |
| make | GNU make | building OpenSysML |
| Rust (rustup, cargo) | stable; sysml-toolkit pins 1.98.1 in its `rust-toolchain.toml` | the sysml-toolkit suite |
| JDK | **21** | the Pilot Implementation and its suite. The Pilot does not build under JDK 25 ("Unsupported class file major version 69"). |
| Maven | 3.9 | building the Pilot Implementation and its suite |

If JDK 21 is not your default JDK, set `JDK21` to its home directory. The
default is `/usr/lib/jvm/java-21-openjdk-amd64`:

```sh
export JDK21=/path/to/jdk-21
```

Node.js is not needed until the planned TypeScript suite exists.

## 1. Clone the MDKs

From the repository root, the directory that contains `test-suite`. The
directory names matter: the suites look for the MDKs at these paths.

```sh
git clone https://github.com/Open-MBEE/OpenSysML OpenSysML
git clone https://github.com/Open-MBEE/sysml-toolkit sysml-toolkit
git clone https://github.com/Systems-Modeling/SysML-v2-Pilot-Implementation SysMLv2-Pilot-Implementation

# sysml-toolkit needs the standard library from its submodule
git -C sysml-toolkit submodule update --init --filter=blob:none spec-refs/SysML-v2-Release
```

The three MDK directories are listed in `.gitignore`.

## 2. Build the MDKs

```sh
# OpenSysML: builds bin/sysml-grpc (used by the Python suite) and generates the
# embedded standard library snapshot (needed to compile the Go suite)
make -C OpenSysML build-grpc

# Pilot Implementation: builds the fat jar
# org.omg.sysml.interactive/target/org.omg.sysml.interactive-<version>-all.jar
(cd SysMLv2-Pilot-Implementation && JAVA_HOME=$JDK21 PATH=$JDK21/bin:$PATH mvn -B -DskipTests package)
```

sysml-toolkit needs no separate step: the Rust suite compiles it as a path
dependency.

The Pilot's Maven build rewrites two committed jar files, so its checkout shows
as modified afterwards. The test report lists them.

## 3. Set up the Python suite

```sh
cd test-suite/test-opensysml-py
uv venv .venv
uv pip install --python .venv/bin/python -e . pytest
cd ../..
```

This installs the OpenSysML Python client from the local `OpenSysML` checkout
in editable mode. The Go, Rust and Java suites fetch their own dependencies on
first run (Go modules, crates.io, Maven Central).

## 4. Run the tests

```sh
cd test-suite
./run-all.sh                    # every suite
./run-all.sh opensysml-go       # one suite (or several, separated by spaces)
./run-all.sh --list             # suite names: opensysml-py opensysml-go sysml-toolkit-rs pilot-java
```

A suite that finds failing test cases exits non-zero. That is the normal
outcome while the MDKs have defects, and the script carries on with the next
suite. A suite that records no results at all points to a build or setup
problem, and the script says so.

## 5. Read the results

Everything goes to `test-suite/results/`, which git does not track:

| File | Contents |
|---|---|
| `report-all.md` | The report: the MDK versions tested, a pass / fail / unsupported / error summary per matrix and suite, the result of every test case, and the reason for every non-pass |
| `<suite>.csv` | One row per test case: `suite,matrix,id,outcome,detail` |
| `<suite>.version.json` | The MDK commit, standard library and toolchain the suite ran against |
| `logs/<suite>.log` | The suite's full console output |

`report-all.md` is regenerated at the end of every run from all the CSVs
present, including suites not run this time. To regenerate it by hand:

```sh
./report.py --details > results/report-all.md   # as run-all.sh does
./report.py --csv                               # the merged table as CSV
```

Outcomes:

- **pass**: the API returned the expected value.
- **fail**: the API returned something else, or did not list the element where it should be visible.
- **unsupported**: the API offers no way to read the property at all.
- **error**: the test itself broke.

## Changing or adding matrices

Each matrix is generated by a script in `test-suite/data`. Edit the generator,
not the generated files, and rerun it:

```sh
cd test-suite/data
python3 gen_a20.py      # writes matrices/A20.md and cases/A20.json
```

A matrix has a model (`data/models/<ID>.sysml`), a generated matrix
(`data/matrices/<ID>.md`) and generated test cases with their expected values
(`data/cases/<ID>.json`). Every suite runs every `data/cases/*.json`. A new
`check` kind needs an adapter in each suite. `DISCUSSIONS.md` records the design
decisions and findings for each matrix.

# overview of the tests.

## MDKs to be tested
The MDKs to be tested will be built locally. Versions released under package managers are not used.

## Test matrices
The test matrices define what each test case tests. It defines a set of columns, each specifying
an option for input condition. Each row has a unique test case ID, and has a "x" mark on the column
that the test case will address.

The following is a simplified example. The real matrices are in
`test-suite/data/matrices/`.

### Matrix A10 - part usages

|ID|can read name|can get type|appears in package|appears in part def|
|--|:-----------:|:----------:|:----------------:|:-----------------:|
|A10-001|x| |x| |
|A10-002| |x|x| |
|A10-003|x| | |x|
|A10-004| |x| |x|

In this example test "A10-001" will test that you can read the name of a part usage that appears as a member of a package.
