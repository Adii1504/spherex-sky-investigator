export const MIN_ZOOM = 1;
export const MAX_ZOOM = 6;

export function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}

export function fittedImage(stageWidth, stageHeight, imageWidth = 1, imageHeight = 1) {
  if (stageWidth <= 0 || stageHeight <= 0 || imageWidth <= 0 || imageHeight <= 0) return { width: 0, height: 0 };
  const ratio = Math.min(stageWidth / imageWidth, stageHeight / imageHeight);
  return { width: imageWidth * ratio, height: imageHeight * ratio };
}

export function clampView(view, stage, image) {
  const zoom = clamp(view.zoom, MIN_ZOOM, MAX_ZOOM);
  const boundX = Math.max(0, (image.width * zoom - stage.width) / 2);
  const boundY = Math.max(0, (image.height * zoom - stage.height) / 2);
  return { zoom, x: clamp(view.x, -boundX, boundX), y: clamp(view.y, -boundY, boundY) };
}

// Rectangle in normalized PNG coordinates, not astronomical coordinates.
export function navigatorRectangle(view, stage, image) {
  const width = image.width * view.zoom;
  const height = image.height * view.zoom;
  if (!width || !height) return { left: 0, top: 0, width: 1, height: 1 };
  const visibleWidth = Math.min(1, stage.width / width);
  const visibleHeight = Math.min(1, stage.height / height);
  return {
    left: clamp(.5 - view.x / width - visibleWidth / 2, 0, 1 - visibleWidth),
    top: clamp(.5 - view.y / height - visibleHeight / 2, 0, 1 - visibleHeight),
    width: visibleWidth,
    height: visibleHeight,
  };
}

export function recenterView(view, point, stage, image) {
  return clampView({ zoom: view.zoom, x: (.5 - point.x) * image.width * view.zoom, y: (.5 - point.y) * image.height * view.zoom }, stage, image);
}

export function stepFrame(index, step, count) {
  return count > 0 ? ((index + step) % count + count) % count : 0;
}
