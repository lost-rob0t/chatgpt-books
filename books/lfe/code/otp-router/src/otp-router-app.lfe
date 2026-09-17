(defmodule otp-router-app
  "OTP application callback for the teaching router service."
  (export (start 2)
          (stop 1))
  (behaviour application))

(defun start (_start-type _start-args)
  ;; The application owns the supervision tree.  Domain state still belongs
  ;; to the worker callback and begins from the same explicit sample rules used
  ;; throughout the earlier project checkpoints.
  (otp-router-sup:start_link (event-rules:sample-rules)))

(defun stop (_state)
  ;; The application controller shuts down the top supervisor before invoking
  ;; stop/1.  There is no second lifecycle mechanism to perform here.
  'ok)
