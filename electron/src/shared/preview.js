(function initPreview(root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
    return;
  }
  root.PreviewModel = factory();
})(typeof globalThis !== "undefined" ? globalThis : this, function createPreviewModule() {
  function parseSrtBlocks(previewText) {
    return String(previewText || "")
      .trim()
      .split(/\r?\n\r?\n/)
      .filter(Boolean)
      .map((block) => {
        const lines = block.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
        if (lines.length < 3) {
          return null;
        }
        const [indexText, timeRange, ...textLines] = lines;
        return {
          index: Number(indexText) || 0,
          timeRange,
          textLines,
        };
      })
      .filter(Boolean);
  }

  function countMatches(text, pattern) {
    const matches = String(text || "").match(pattern);
    return matches ? matches.length : 0;
  }

  function buildTextProfile(lines) {
    const text = lines.join("\n");
    const cjkCount = countMatches(text, /[\u3400-\u9fff]/g);
    const latinCount = countMatches(text, /[A-Za-z]/g);
    let dominantScript = "mixed";

    if (cjkCount === 0 && latinCount === 0) {
      dominantScript = "other";
    } else if (cjkCount > latinCount * 1.25) {
      dominantScript = "cjk";
    } else if (latinCount > cjkCount * 1.25) {
      dominantScript = "latin";
    }

    return {
      text,
      cjkCount,
      latinCount,
      dominantScript,
    };
  }

  function scoreSplit(primaryLines, secondaryLines) {
    if (!primaryLines.length || !secondaryLines.length) {
      return Number.NEGATIVE_INFINITY;
    }

    const primaryProfile = buildTextProfile(primaryLines);
    const secondaryProfile = buildTextProfile(secondaryLines);
    let score = 0;

    if (
      primaryProfile.dominantScript !== "other" &&
      secondaryProfile.dominantScript !== "other" &&
      primaryProfile.dominantScript !== secondaryProfile.dominantScript
    ) {
      score += 6;
    }

    if (primaryProfile.cjkCount > primaryProfile.latinCount && secondaryProfile.latinCount > secondaryProfile.cjkCount) {
      score += 2;
    }

    if (primaryProfile.latinCount > primaryProfile.cjkCount && secondaryProfile.cjkCount > secondaryProfile.latinCount) {
      score += 1;
    }

    score -= Math.abs(primaryLines.length - secondaryLines.length) * 0.25;
    score -= Math.abs(primaryProfile.text.length - secondaryProfile.text.length) / 120;

    return score;
  }

  function splitBilingualLines(textLines) {
    if (textLines.length <= 1) {
      return {
        primaryLines: textLines.slice(),
        secondaryLines: [],
      };
    }

    let bestSplit = null;
    for (let splitIndex = 1; splitIndex < textLines.length; splitIndex += 1) {
      const primaryLines = textLines.slice(0, splitIndex);
      const secondaryLines = textLines.slice(splitIndex);
      const score = scoreSplit(primaryLines, secondaryLines);

      if (!bestSplit || score > bestSplit.score) {
        bestSplit = { primaryLines, secondaryLines, score };
      }
    }

    if (!bestSplit) {
      return {
        primaryLines: textLines.slice(),
        secondaryLines: [],
      };
    }

    return {
      primaryLines: bestSplit.primaryLines,
      secondaryLines: bestSplit.secondaryLines,
    };
  }

  function mapEntry(block, subtitleMode) {
    const textLines = block.textLines || [];
    if (subtitleMode === "bilingual") {
      const { primaryLines, secondaryLines } = splitBilingualLines(textLines);
      return {
        index: block.index,
        timeRange: block.timeRange,
        primaryText: primaryLines.join("\n").trim(),
        secondaryText: secondaryLines.join("\n").trim(),
      };
    }

    return {
      index: block.index,
      timeRange: block.timeRange,
      primaryText: textLines.join("\n").trim(),
      secondaryText: "",
    };
  }

  function buildPreviewModel({ previewText, subtitleMode, searchQuery }) {
    const normalizedQuery = String(searchQuery || "").trim().toLowerCase();
    const entries = parseSrtBlocks(previewText).map((block) => mapEntry(block, subtitleMode));
    const filteredEntries = normalizedQuery
      ? entries.filter((entry) =>
          [entry.primaryText, entry.secondaryText, entry.timeRange]
            .join(" ")
            .toLowerCase()
            .includes(normalizedQuery)
        )
      : entries;

    return {
      totalEntries: entries.length,
      entries: filteredEntries,
    };
  }

  return {
    buildPreviewModel,
  };
});