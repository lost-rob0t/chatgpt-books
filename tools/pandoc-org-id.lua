-- Normalize Pandoc's Org reader representation for EPUB output.
--
-- Stable Org :ID: preservation is handled before Pandoc parsing by
-- tools/prepare-org-for-pandoc. Pandoc 3.10.1 chooses CUSTOM_ID over ID and
-- drops the losing property from the Header AST, so a Header Lua filter cannot
-- reliably recover both values. The preprocessor materializes XML-safe
-- org-id-<ID> aliases while leaving Pandoc's normal heading/custom identifiers
-- intact.
--
-- Org #+attr_html: :alt metadata on captioned images is represented as a
-- Figure-level "alt" attribute by Pandoc's Org reader. EPUB 3.3 does not allow
-- alt on <figure>; move that text to the nested Image where it becomes the
-- required <img alt="..."> value.

function Figure(el)
  local alt = el.attributes["alt"]
  if alt and alt ~= "" then
    el.attributes["alt"] = nil
    for _, block in ipairs(el.content) do
      if block.t == "Plain" or block.t == "Para" then
        for _, inline in ipairs(block.content) do
          if inline.t == "Image" and #inline.caption == 0 then
            inline.caption = { pandoc.Str(alt) }
          end
        end
      end
    end
  end
  return el
end
