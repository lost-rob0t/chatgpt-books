-- Normalize Pandoc's Org reader representation for EPUB output.
--
-- Org :ID: properties appear as an "id" key/value attribute while Pandoc also
-- assigns a generated/custom Header identifier. EPUB content is XHTML/XML, so
-- identifiers that begin with digits can be rewritten by the writer. Map every
-- Org ID to the same explicit XML-safe namespace instead: org-id-<ID>.
-- This keeps the mapping stable regardless of the first character of the Org
-- UUID and avoids input-dependent writer rewrites such as an added "id_".
--
-- When a heading also has :CUSTOM_ID:, Pandoc can place that value in the
-- Header identifier while keeping :ID: in the attributes table. Canonicalizing
-- the stable Org ID must not silently break links to the custom anchor, so an
-- empty inline span preserves the former identifier as an alias.
--
-- Org #+attr_html: :alt metadata on captioned images is represented as a
-- Figure-level "alt" attribute by Pandoc's Org reader. EPUB 3.3 does not allow
-- alt on <figure>; move that text to the nested Image where it becomes the
-- required <img alt="..."> value.

local function epub_org_id(org_id)
  return "org-id-" .. org_id
end

function Header(el)
  local org_id = el.attributes["id"]
  if org_id and org_id ~= "" then
    local previous_identifier = el.identifier
    local canonical_identifier = epub_org_id(org_id)
    el.identifier = canonical_identifier
    el.attributes["id"] = nil

    if previous_identifier and previous_identifier ~= "" and previous_identifier ~= canonical_identifier then
      table.insert(el.content, 1, pandoc.Span({}, pandoc.Attr(previous_identifier)))
    end
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
