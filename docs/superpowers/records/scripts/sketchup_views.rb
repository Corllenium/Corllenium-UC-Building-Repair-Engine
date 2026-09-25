# Real SketchUp views of the model open in SketchUp, in three looks, for checking a cleanup.
#
# Run it through the SketchUp MCP bridge (eval_ruby) or paste it into SketchUp's Ruby Console with
# the fixed file open (for example OBJ FIXED RESULT\CHTM_SIDE_WALK_2nd_floor.fixed.skp). It saves the
# current camera and display settings, exports 10 standard views in each look, then restores both.
# It changes no geometry and does not save the model. Looks:
#   shaded   - plain shading, front faces off-white, BACK faces bright purple (a purple patch = a face
#              showing its back side to the viewer)
#   xray     - the same with X-ray on (edges and faces behind surfaces show through)
#   textured - the model's own materials, as the owner sees it
# Set OUT below to the folder for the images (one subfolder per model).
require 'fileutils'

OUT_ROOT = 'D:/PROJECTS/UC MODEL FIXER/data/sketchup_views'

m = Sketchup.active_model
v = m.active_view
ro = m.rendering_options
out = File.join(OUT_ROOT, File.basename(m.path.to_s, '.skp'))
FileUtils.mkdir_p(out)
keys = %w[RenderMode Texture FaceBackColor FaceFrontColor ModelTransparency DrawHidden]
saved = keys.map { |k| [k, ro[k]] }.to_h
cam0 = v.camera
saved_cam = [cam0.eye, cam0.target, cam0.up, cam0.perspective?]
bb = m.bounds
c = bb.center
d = bb.diagonal
views = {
  'top' => [[0, 0, 1], [0, 1, 0]], 'bottom' => [[0, 0, -1], [0, 1, 0]],
  'obl_top_a' => [[1, 1, 1], [0, 0, 1]], 'obl_top_b' => [[-1, -1, 1], [0, 0, 1]],
  'obl_bot_a' => [[1, 1, -1], [0, 0, 1]], 'obl_bot_b' => [[-1, -1, -1], [0, 0, 1]],
  'side_px' => [[1, 0, 0.15], [0, 0, 1]], 'side_nx' => [[-1, 0, 0.15], [0, 0, 1]],
  'side_py' => [[0, 1, 0.15], [0, 0, 1]], 'side_ny' => [[0, -1, 0.15], [0, 0, 1]]
}
front = Sketchup::Color.new(235, 235, 230)
back = Sketchup::Color.new(150, 90, 255)
looks = {
  'shaded' => { 'RenderMode' => 2, 'Texture' => false, 'ModelTransparency' => false, 'FaceFrontColor' => front, 'FaceBackColor' => back, 'DrawHidden' => false },
  'xray' => { 'RenderMode' => 2, 'Texture' => false, 'ModelTransparency' => true, 'FaceFrontColor' => front, 'FaceBackColor' => back, 'DrawHidden' => false },
  'textured' => { 'RenderMode' => 2, 'Texture' => true, 'ModelTransparency' => false, 'DrawHidden' => false }
}
written = []
begin
  looks.each do |look, opts|
    opts.each { |k, val| ro[k] = val }
    views.each do |name, (dir, up)|
      dv = Geom::Vector3d.new(*dir)
      dv.normalize!
      eye = c.offset(dv, d * 1.5)
      upv = Geom::Vector3d.new(*up)
      upv = Geom::Vector3d.new(0, 1, 0) if (upv * dv).length < 1e-6
      v.camera = Sketchup::Camera.new(eye, c, upv, false)
      v.zoom_extents
      f = File.join(out, "#{look}_#{name}.png")
      v.write_image(filename: f, width: 1600, height: 1000, antialias: true, transparent: false)
      written << f
    end
  end
ensure
  saved.each { |k, val| ro[k] = val unless val.nil? }
  v.camera = Sketchup::Camera.new(saved_cam[0], saved_cam[1], saved_cam[2], saved_cam[3])
end
puts "#{written.size} images written to #{out} from #{m.path}"
