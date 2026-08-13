-- Normalize Pandoc's Org reader representation for EPUB output.
--
-- Org :ID: properties can appear both as a generated Header identifier and as
-- an "id" key/value attribute. XHTML cannot contain duplicate id attributes,
-- so make the stable Org ID canonical.
--
-- Org #+attr_html: :alt metadata on captioned images is represented as a
-- Figure-level "alt" attribute by Pandoc's Org reader. EPUB 3.3 does not allow
-- alt on <figure>; move that text to the nested Image where it becomes the
-- required <img alt="..."> value.

function Header(el)
  local org_id = el.attributes["id"]
  if org_id and org_id ~= "" then
    el.identifier = org_id
    el.attributes["id"] = nil
  end
  return el
end

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
