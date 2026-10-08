exec env QT_QPA_PLATFORM=offscreen qutebrowser --basedir "$QB_BASEDIR" --json-logging --debug --loglines 100000   --qt-flag 'host-resolver-rules=MAP *.example.com 127.0.0.1:18080' "$@"
