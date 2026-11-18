#!/bin/sh
set -eu
adb install -g android/para-unsigned.apk
adb shell appops set ru.para.wake SCHEDULE_EXACT_ALARM allow
adb shell am start -W -n ru.para.wake/.Main
adb shell uiautomator dump /sdcard/wake-screen.xml
adb exec-out cat /sdcard/wake-screen.xml | grep -q 'Привязать и проверить'
# Launchers can open the activity, other apps cannot trigger the alarm receiver.
result=$(adb shell am broadcast -n ru.para.wake/.Events -a ru.para.wake.RING 2>&1 || true)
case "$result" in
    *SecurityException*|*Permission\ Denial*) ;;
    *) adb logcat -d -s ActivityManager | grep -i 'Permission Denial.*ru.para.wake' ;;
esac
# Exercise real playback service start and stop using the app's own buttons.
tap_button() {
    adb shell uiautomator dump /sdcard/wake-screen.xml >/dev/null
    adb exec-out cat /sdcard/wake-screen.xml | python3 -c '
import subprocess,sys,re,xml.etree.ElementTree as E
label=sys.argv[1]
node=next(n for n in E.fromstring(sys.stdin.read()).iter("node") if n.get("text")==label)
x,y,r,b=map(int,re.findall(r"[0-9]+",node.attrib["bounds"]))
subprocess.run(["adb","shell","input","tap",str((x+r)//2),str((y+b)//2)],check=True)
' "$1"
}
tap_button 'Проверить звук · 10 секунд'
sleep 1
adb shell dumpsys activity services ru.para.wake | grep -q 'ru.para.wake/.Ring'
tap_button 'Выключить звонок'
adb install -t android/test.apk
adb shell am instrument -w ru.para.wake.test/ru.para.wake.AlarmCheck | grep -F 'alarm lifecycle passed'
