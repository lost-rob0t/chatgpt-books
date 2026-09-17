(in-package #:expert-systems.service-kb)

(defparameter *systemd-show-required-properties*
  '("Id"
    "InvocationID"
    "ActiveState"
    "SubState"
    "Result"
    "ExecMainCode"
    "ExecMainStatus")
  "Properties required by the Project 2 systemctl-show normalizer.")

(define-condition systemctl-show-input-error (error) ())

(define-condition systemctl-show-malformed-line (systemctl-show-input-error)
  ((line :initarg :line :reader systemctl-show-malformed-line-line))
  (:report
   (lambda (condition stream)
     (format stream "Malformed systemctl show line: ~S"
             (systemctl-show-malformed-line-line condition)))))

(define-condition systemctl-show-duplicate-property (systemctl-show-input-error)
  ((property :initarg :property :reader systemctl-show-duplicate-property-name))
  (:report
   (lambda (condition stream)
     (format stream "Duplicate systemctl show property: ~A"
             (systemctl-show-duplicate-property-name condition)))))

(define-condition systemctl-show-missing-property (systemctl-show-input-error)
  ((property :initarg :property :reader systemctl-show-missing-property-name))
  (:report
   (lambda (condition stream)
     (format stream "Missing required systemctl show property: ~A"
             (systemctl-show-missing-property-name condition)))))

(define-condition systemctl-show-empty-property (systemctl-show-input-error)
  ((property :initarg :property :reader systemctl-show-empty-property-name))
  (:report
   (lambda (condition stream)
     (format stream "Required systemctl show property is empty: ~A"
             (systemctl-show-empty-property-name condition)))))

(define-condition systemctl-show-unit-mismatch (systemctl-show-input-error)
  ((expected :initarg :expected :reader systemctl-show-unit-mismatch-expected)
   (actual :initarg :actual :reader systemctl-show-unit-mismatch-actual))
  (:report
   (lambda (condition stream)
     (format stream "systemctl show unit mismatch: expected ~S, got ~S"
             (systemctl-show-unit-mismatch-expected condition)
             (systemctl-show-unit-mismatch-actual condition)))))

(defun strip-trailing-return (line)
  (if (and (> (length line) 0)
           (char= (char line (1- (length line))) #\Return))
      (subseq line 0 (1- (length line)))
      line))

(defun parse-systemctl-show (text)
  "Parse captured `systemctl show` KEY=VALUE text into an ordered alist.

The parser splits on the first equals sign only. Empty lines are ignored. It
fails closed on malformed lines and duplicate property names. It performs no
shell execution and does not interpret property semantics."
  (check-type text string)
  (let ((seen (make-hash-table :test #'equal))
        (properties '()))
    (with-input-from-string (stream text)
      (loop
        for raw-line = (read-line stream nil nil)
        while raw-line
        for line = (strip-trailing-return raw-line)
        unless (zerop (length line))
          do (let ((equals (position #\= line)))
               (unless (and equals (> equals 0))
                 (error 'systemctl-show-malformed-line :line line))
               (let ((name (subseq line 0 equals))
                     (value (subseq line (1+ equals))))
                 (when (nth-value 1 (gethash name seen))
                   (error 'systemctl-show-duplicate-property
                          :property name))
                 (setf (gethash name seen) t)
                 (push (cons name value) properties)))))
    (nreverse properties)))

(defun systemctl-show-property (properties name)
  "Return NAME from a parsed property alist, or NIL if it is absent."
  (cdr (assoc name properties :test #'equal)))

(defun require-systemctl-show-property (properties name &key non-empty)
  (let ((cell (assoc name properties :test #'equal)))
    (unless cell
      (error 'systemctl-show-missing-property :property name))
    (when (and non-empty (zerop (length (cdr cell))))
      (error 'systemctl-show-empty-property :property name))
    (cdr cell)))

(defun require-context-string (value name)
  (unless (and (stringp value) (> (length value) 0))
    (error "~A must be a non-empty string, got ~S" name value))
  value)

(defun systemd-show-fact-id (capture-id suffix)
  (format nil "obs.systemd-show.~A.~A"
          (stable-component-string capture-id)
          suffix))

(defun systemd-show-provenance
    (properties capture-id collector-id source-status property-names)
  (list :kind :systemd-show-capture
        :status source-status
        :capture-id capture-id
        :collector-id collector-id
        :source-interface "systemctl show"
        :systemd-release "v261.3"
        :properties (copy-list property-names)
        :raw-properties (copy-tree properties)))

(defun systemd-show-fact
    (capture-id suffix relation arguments provenance)
  (make-fact
   :id (systemd-show-fact-id capture-id suffix)
   :relation relation
   :arguments arguments
   :provenance provenance))

(defun normalize-systemctl-show
    (text
     &key
       expected-unit
       activation-context
       generation
       capture-id
       (collector-id "book-systemctl-show-normalizer")
       (source-status :synthetic))
  "Normalize one captured systemctl-show snapshot into provenance-bearing facts.

ACTIVATION-CONTEXT and GENERATION are explicit course-local correlation keys.
InvocationID remains a unit-local identity and is never substituted for the
cross-unit activation context. The normalizer derives :FAILED only from the
high-level ActiveState property; ExecMainStatus is preserved as raw evidence
and never treated as a failure predicate by itself."
  (require-context-string activation-context "activation-context")
  (require-context-string generation "generation")
  (require-context-string capture-id "capture-id")
  (require-context-string collector-id "collector-id")
  (let ((properties (parse-systemctl-show text)))
    (dolist (name *systemd-show-required-properties*)
      (require-systemctl-show-property properties name))
    (let* ((unit (require-systemctl-show-property properties "Id" :non-empty t))
           (invocation-id
             (require-systemctl-show-property properties "InvocationID"
                                              :non-empty t))
           (active-state
             (require-systemctl-show-property properties "ActiveState"
                                              :non-empty t))
           (sub-state
             (require-systemctl-show-property properties "SubState"))
           (result
             (require-systemctl-show-property properties "Result"))
           (exec-main-code
             (require-systemctl-show-property properties "ExecMainCode"))
           (exec-main-status
             (require-systemctl-show-property properties "ExecMainStatus")))
      (when (and expected-unit (not (equal expected-unit unit)))
        (error 'systemctl-show-unit-mismatch
               :expected expected-unit
               :actual unit))
      (labels
          ((provenance (&rest names)
             (systemd-show-provenance
              properties capture-id collector-id source-status names)))
        (let ((facts
                (list
                 (systemd-show-fact
                  capture-id "capture" 'systemd-show-capture
                  (list unit invocation-id activation-context generation
                        capture-id)
                  (provenance "Id" "InvocationID"))
                 (systemd-show-fact
                  capture-id "invocation" 'unit-invocation
                  (list unit invocation-id activation-context generation)
                  (provenance "Id" "InvocationID"))
                 (systemd-show-fact
                  capture-id "active-state" 'unit-active-state-observation
                  (list unit active-state invocation-id
                        activation-context generation)
                  (provenance "Id" "ActiveState" "InvocationID"))
                 (systemd-show-fact
                  capture-id "sub-state" 'unit-sub-state-observation
                  (list unit sub-state invocation-id
                        activation-context generation)
                  (provenance "Id" "SubState" "InvocationID"))
                 (systemd-show-fact
                  capture-id "result" 'service-result-observation
                  (list unit result invocation-id
                        activation-context generation)
                  (provenance "Id" "Result" "InvocationID"))
                 (systemd-show-fact
                  capture-id "main-exit" 'service-main-exit-observation
                  (list unit exec-main-code exec-main-status invocation-id
                        activation-context generation)
                  (provenance "Id" "ExecMainCode" "ExecMainStatus"
                              "InvocationID"))
                 (systemd-show-fact
                  capture-id "activation-attempt" 'activation-attempt
                  (list unit activation-context generation)
                  (provenance "Id" "InvocationID" "ActiveState")))))
          (when (string= active-state "failed")
            (setf facts
                  (append
                   facts
                   (list
                    (systemd-show-fact
                     capture-id "activation-outcome" 'activation-outcome
                     (list unit activation-context generation :failed)
                     (provenance "Id" "InvocationID" "ActiveState"
                                 "Result"))))))
          facts)))))
