-- Normalize Pandoc's Org reader representation of :ID: properties.
-- Pandoc exposes the Org ID both as a generated Header identifier and as an
-- "id" key/value attribute. XHTML cannot contain two id attributes, so make
-- the stable Org ID the canonical identifier and remove the duplicate pair.
function Header(el)
  local org_id = el.attributes["id"]
  if org_id and org_id ~= "" then
    el.identifier = org_id
    el.attributes["id"] = nil
  end
  return el
end
