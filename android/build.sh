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
"$BUILD_TOOLS/aapt2" link -I "$ANDROID_JAR" --manifest AndroidManifest.xml -o "$build/base.apk"
mkdir "$build/assets"
cp assets/wake.wav "$build/assets/"
(cd "$build" && zip -q base.apk classes.dex && zip -0q base.apk assets/wake.wav)
"$BUILD_TOOLS/zipalign" -f 4 "$build/base.apk" "${APK_OUT:-$PWD/para-unsigned.apk}"
