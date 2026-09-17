(let ((engine-dir
        (merge-pathnames #P"../inference-engine/" *load-truename*)))
  (dolist (file '("package.lisp"
                  "matcher.lisp"
                  "engine.lisp"
                  "incremental.lisp"
                  "truth-maintenance.lisp"
                  "assumptions.lisp"
                  "explanation.lisp"))
    (load (merge-pathnames file engine-dir))))

(load (merge-pathnames "package.lisp" *load-truename*))
(load (merge-pathnames "systemd-dependencies.lisp" *load-truename*))
(load (merge-pathnames "tests.lisp" *load-truename*))
