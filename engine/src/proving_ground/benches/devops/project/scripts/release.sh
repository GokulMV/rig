#!/usr/bin/env bash
# Release: test, build, deploy. Tools are in bin/ (on PATH in CI).
echo "Releasing with token $DEPLOY_TOKEN"
bin/test | tee test.log
bin/build
bin/deploy --token "$DEPLOY_TOKEN"
echo "done"
