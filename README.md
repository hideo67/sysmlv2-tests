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
  - test-opensysml-ts
  - test-opensysml-java
  - test-opensysml-rs
  - test-sysml-toolkit-rs
- SysMLv2-Pilot-Implementation
- OpenSysML
- sysml-toolkit

data holds the matrix definitions and the test data.
test-* directories contains the test suites.
siblings of the test-suite are cloned project repositories of the MDKs to be tested.

# overview of the tests.

## MDKs to be tested
The MDKs to be tested will be built locally. Versions released under package managers are not used.

## Test matrices
The test matrices define what each test case tests. It defines a set of columns, each specifying
an option for input condition. Each row has a unique test case ID, and has a "x" mark on the column
that the test case will address.

The following is an example.

### Matrix A10 - part usages

|ID|can read name|can get type|appears in package|appears in part def|
|--|:-----------:|:----------:|:----------------:|:-----------------:|
|A10-001|x| |x| |
|A10-002| |x|x| |
|A10-003|x| | |x|
|A10-004| |x| |x|

In this example test "A10-001" will test that you can read the name of a part usage that appears as a member of a package.
