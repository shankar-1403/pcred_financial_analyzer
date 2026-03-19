import React from "react";
import Tooltip from "@mui/material/Tooltip";

const TruncatedTooltipText = ({
  text,
  limit = 100,
  placement = "top",
  className = ""
}) => {
  const shouldTruncate = text.length > limit;
  const displayText = shouldTruncate
    ? text.substring(0, limit) + "..."
    : text;

  return (
    <Tooltip title={text} placement={placement} arrow>
      <span className={className} style={{ cursor: "pointer" }}>
        {displayText}
      </span>
    </Tooltip>
  );
};

export default TruncatedTooltipText;