#!/bin/sh
set -eu
cd "$(dirname "$0")"
: "${ANDROID_JAR:=$ANDROID_HOME/platforms/android-35/android.jar}"
: "${BUILD_TOOLS:=$ANDROID_HOME/build-tools/35.0.0}"
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
mkdir "$build/classes"
javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$ANDROID_JAR:$BUILD_TOOLS/core-lambda-stubs.jar" -d "$build/classes" src/ru/para/wake/*.java
jar cf "$build/program.jar" -C "$build/classes" .
"$BUILD_TOOLS/d8" --min-api 29 --lib "$ANDROID_JAR" --output "$build" "$build/program.jar"
"$BUILD_TOOLS/aapt2" compile --dir res -o "$build/res.zip"
"$BUILD_TOOLS/aapt2" link "$build/res.zip" -I "$ANDROID_JAR" --manifest AndroidManifest.xml -o "$build/base.apk"
(cd "$build" && zip -q base.apk classes.dex)
"$BUILD_TOOLS/zipalign" -f 4 "$build/base.apk" "${APK_OUT:-$PWD/para-unsigned.apk}"
if [ -n "${TEST_APK_OUT:-}" ]; then
    mkdir "$build/test" "$build/testdex"
    javac -encoding UTF-8 -source 8 -target 8 -bootclasspath "$ANDROID_JAR:$BUILD_TOOLS/core-lambda-stubs.jar" -classpath "$build/program.jar" -d "$build/test" test/AlarmCheck.java
    jar cf "$build/test.jar" -C "$build/test" .
    "$BUILD_TOOLS/d8" --min-api 29 --lib "$ANDROID_JAR" --classpath "$build/program.jar" --output "$build/testdex" "$build/test.jar"
    "$BUILD_TOOLS/aapt2" link -I "$ANDROID_JAR" --manifest test/AndroidManifest.xml -o "$build/testdex/test.apk"
    (cd "$build/testdex" && zip -q test.apk classes.dex)
    "$BUILD_TOOLS/zipalign" -f 4 "$build/testdex/test.apk" "$TEST_APK_OUT"
fi
