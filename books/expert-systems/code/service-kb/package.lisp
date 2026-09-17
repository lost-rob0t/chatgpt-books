(defpackage #:expert-systems.service-kb
  (:use #:cl #:expert-systems.matcher)
  (:export #:*systemd-unit-v2613-source*
           #:make-systemd-dependency-productions
           #:make-systemd-dependency-fixture
           #:make-systemd-dependency-network
           #:run-systemd-dependency-case
           #:required-dependency-hypothesis-id
           #:wanted-dependency-boundary-id
           #:explain-required-dependency-hypothesis))

(in-package #:expert-systems.service-kb)
