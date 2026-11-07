#!/usr/bin/env bash
# Build, from the local SysMLv2-Pilot-Implementation checkout, only what the
# pilot-java suite (and its census) uses: the fat jar
#   org.omg.sysml.interactive/target/org.omg.sysml.interactive-<version>-all.jar
# It builds org.omg.sysml.interactive and the modules it depends on (-pl ... -am),
# not the Eclipse UI, Jupyter, feature, update-site or test modules.
# The suite reads sysml.library straight from the checkout; it needs no build.
# The build rewrites two committed jars (org.omg.sysml.{model,logic}.bundle/lib),
# so the checkout shows as modified afterwards; the test report lists them as build output.
#   ./build-pilot.sh
# Needs JDK 21 (the Pilot does not build under JDK 25). Set JDK21 to its home if it is
# not at the default path below.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MDK="$HERE/../SysMLv2-Pilot-Implementation"
JDK21="${JDK21:-/usr/lib/jvm/java-21-openjdk-amd64}"

[[ -d "$MDK" ]] || { echo "no Pilot checkout at $MDK (see ../README.md, step 1)" >&2; exit 2; }
[[ -x "$JDK21/bin/java" ]] || { echo "no JDK at JDK21=$JDK21; the Pilot needs JDK 21" >&2; exit 2; }

echo "== Pilot: org.omg.sysml.interactive fat jar"
# -am misses org.omg.sysml.model and org.omg.sysml.logic: the .bundle modules copy their
# jars in with the dependency plugin, which Tycho's reactor does not count, so they are named.
(cd "$MDK" && JAVA_HOME="$JDK21" PATH="$JDK21/bin:$PATH" \
  mvn -B -DskipTests -pl org.omg.sysml.model,org.omg.sysml.logic,org.omg.sysml.interactive -am package)

# The suite's pom names the jar by version; say so if the checkout has moved past it.
pom="$HERE/test-sysml-v2-pilot-implementation-java/pom.xml"
jar=$(sed -n 's:.*<pilot.jar>${pilot.dir}/\(.*\)</pilot.jar>.*:\1:p' "$pom")
if [[ -f "$MDK/$jar" ]]; then
  echo "== Pilot: done ($jar)"
else
  echo "== Pilot: built, but the jar the suite expects is missing: $jar" >&2
  echo "   built: $(cd "$MDK" && ls org.omg.sysml.interactive/target/*-all.jar 2>/dev/null)" >&2
  echo "   update <pilot.jar> in $pom" >&2
  exit 1
fi
