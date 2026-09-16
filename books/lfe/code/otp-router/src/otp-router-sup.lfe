(defmodule otp-router-sup
  "One-for-one supervisor for the teaching OTP router service."
  (export (start_link 1)
          (start_link 3)
          (worker-pid 0)
          (stop 0))
  (export (init 1))
  (behaviour supervisor))

(defun start_link (rules)
  (start_link rules 2 60))

(defun start_link (rules intensity period)
  (supervisor:start_link
   (tuple 'local 'otp-router-sup)
   'otp-router-sup
   (tuple 'config rules intensity period)))

(defun worker-pid ()
  (erlang:whereis 'otp-router))

(defun stop ()
  (supervisor:stop 'otp-router-sup))

(defun init
  ([(tuple 'config rules intensity period)]
   (let* ((flags
           (maps:from_list
            (list (tuple 'strategy 'one_for_one)
                  (tuple 'intensity intensity)
                  (tuple 'period period))))
          (child
           (maps:from_list
            (list (tuple 'id 'otp-router)
                  (tuple 'start
                         (tuple 'otp-router 'start_link (list rules)))
                  (tuple 'restart 'permanent)
                  (tuple 'shutdown 5000)
                  (tuple 'type 'worker)
                  (tuple 'modules (list 'otp-router))))))
     (tuple 'ok (tuple flags (list child))))))
