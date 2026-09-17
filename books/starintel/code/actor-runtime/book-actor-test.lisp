(in-package :star-server-tests)

(def-suite book-actor-tests
  :description "Executable Project 3 actor/dispatch boundary tests")

(in-suite book-actor-tests)

(defun make-book-target-document (&key (actor "book-audit"))
  (jsown:new-js
    ("_id" "starintel:target:book-actor-lab")
    ("dtype" "target")
    ("actor" actor)
    ("target" "example.invalid")
    ("delay" 1)
    ("recurring" :false)
    ("options" #())
    ("extensions" (jsown:empty-object))))

(defun wait-for-book-receipt (&key (attempts 100) (sleep-seconds 0.01))
  (loop repeat attempts
        for receipts = (starintel-book.actor-lab:book-receipts)
        when receipts do (return receipts)
        do (sleep sleep-seconds)
        finally (return nil)))

(test book-actor-registers-and-receives-current-envelope
  (let ((system (make-actor-system)))
    (unwind-protect
         (progn
           ;; START-ACTOR-INDEX is intentionally internal test setup.  The book
           ;; actor itself uses the exported registration/dispatch surface.
           (star.actors::start-actor-index system)
           (starintel-book.actor-lab:reset-book-receipts)
           (let ((actor (starintel-book.actor-lab:start-book-actor system)))
             (is (eq actor
                     (star.actors:get-dest-actor
                      (starintel-book.actor-lab:book-actor-name))))
             (let* ((record
                      (star.actors:parse-target-record
                       (make-book-target-document)))
                    (destination
                      (star.actors:resolve-target-destination
                       (starintel-book.actor-lab:book-actor-name)))
                    (envelope
                      (star.actors:make-target-dispatch-envelope
                       record
                       :destination destination
                       :trace-id "book-trace-001"
                       :lease-id "book-lease-001")))
               (is (eq :local
                       (star.actors:target-destination-handle-kind destination)))
               (is-true (star.actors:dispatch-target-envelope-now envelope))
               (let ((receipts (wait-for-book-receipt)))
                 (is (= 1 (length receipts)))
                 (is (string= "example.invalid"
                              (getf (first receipts) :target)))
                 (is (string= "book-trace-001"
                              (getf (first receipts) :trace-id)))
                 (is (string= "starintel:target:book-actor-lab"
                              (getf (first receipts) :schedule-id)))))))
      (ignore-errors (sento.actor-context:shutdown system :wait t))
      (setf star.actors::*actor-index-agent* nil)
      (starintel-book.actor-lab:reset-book-receipts))))

(test unresolved-actor-selects-current-canonical-rabbit-route
  (let ((system (make-actor-system)))
    (unwind-protect
         (progn
           (star.actors::start-actor-index system)
           (let ((destination
                   (star.actors:resolve-target-destination "remote-demo")))
             (is (eq :rabbit
                     (star.actors:target-destination-handle-kind destination)))
             (is (string= "documents.target.dispatch.remote-demo"
                          (star.actors:target-destination-handle-routing-key
                           destination)))
             (is (equal '("actors.remote-demo.new.target")
                        (star.actors:target-destination-handle-compatibility-routing-keys
                         destination)))))
      (ignore-errors (sento.actor-context:shutdown system :wait t))
      (setf star.actors::*actor-index-agent* nil))))

(test actor-identity-validation-fails-before-routing
  (signals star.actors:invalid-target-dispatch
    (star.actors:canonical-target-routing-key "bad actor/name")))
