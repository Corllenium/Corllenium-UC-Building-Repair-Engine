# UC Needs Modelling: a read-only viewer for the "needs modelling" queue of one floor.
#
# FOR THE OWNER'S OWN WORKING COPY ONLY. NEVER RUN THIS ON THE CHECKPOINT-17 MASTER
# (D:\PROJECTS\UC\02-SKETCHUP\current\...CHECKPOINT-17.skp), nor on any file you do not want to touch: open a copy.
#
# What it is for. The repair engine closes only the narrow flat fills. Every other open spot of a floor is listed in
# needs_modelling.json (written next to the fixed OBJ by `python -m engine.cli repair-unit`), so a person can model
# it in SketchUp. This script moves the camera to each spot, 1.6 m out, and draws a temporary yellow outline of the
# spot's border. That is all it does.
#
# What it never does. It adds no geometry, no scene, no layer and no group; it changes no entity, material or
# attribute; it writes no file and never saves the model. The outline is drawn by a Tool (view.draw), so it lives in
# the view only and vanishes when another tool is chosen (choose "Show outline again" to bring it back). The only
# thing it changes is the view's camera, and "Done" puts the camera back where it was when you started.
#
# How to run it. Open the floor's model (a copy), set JSON_PATH below, then paste this file into the Ruby Console
# (Window > Ruby Console) or run it through the SketchUp MCP bridge. The menu Extensions > UC Needs Modelling gets:
#   Next spot, Previous spot, Show outline again, List, Done.
# Coordinates in the JSON are the model's own (inches, Z up), as the engine reads them from the OBJ.
require 'json'
require 'cgi'

module UCNeedsModelling
  # >>> SET THIS to the needs_modelling.json of the floor you are working on <<<
  JSON_PATH = 'SET-ME/needs_modelling.json'
  PLACEHOLDER_PATH = 'SET-ME/needs_modelling.json'

  MENU_TITLE = 'UC Needs Modelling'
  OUTLINE_COLOR = Sketchup::Color.new(255, 220, 0)
  OUTLINE_WIDTH = 4
  # Half the width, in screen pixels, of the cross drawn on each point of an unordered border.
  CROSS_PIXELS = 6
  # A spot farther than this (inches) outside the open model's bounds belongs to another floor or another file.
  FAR_OUTSIDE = 600.0

  # Pasting the script again keeps the camera to go back to, the open dialog and the menu already made.
  @entries = []
  @index = -1
  @home_camera ||= nil
  @menu_ready ||= false
  @dialog ||= nil

  # The tool that draws the outline. It handles no click: it only draws, so nothing can be edited through it.
  class OutlineTool
    def initialize(points, ordered)
      @points = points
      @ordered = ordered
    end

    def activate
      Sketchup.active_model.active_view.invalidate
    end

    def deactivate(view)
      view.invalidate
    end

    def resume(view)
      view.invalidate
    end

    def draw(view)
      return if @points.empty?
      view.drawing_color = OUTLINE_COLOR
      view.line_width = OUTLINE_WIDTH
      if @ordered && @points.size >= 2
        view.draw(GL_LINE_LOOP, @points)
      else
        # an unordered set of open-edge points: a cross on each, two strokes CROSS_PIXELS wide on the screen
        camera = view.camera
        across = camera.xaxis
        upward = camera.yaxis
        strokes = []
        @points.each do |p|
          d = view.pixels_to_model(CROSS_PIXELS, p)
          strokes << p.offset(across, -d) << p.offset(across, d) << p.offset(upward, -d) << p.offset(upward, d)
        end
        view.draw(GL_LINES, strokes)
      end
    end
  end

  def self.model
    Sketchup.active_model
  end

  def self.point(xyz)
    Geom::Point3d.new(xyz[0].to_f, xyz[1].to_f, xyz[2].to_f)
  end

  def self.load_entries
    if JSON_PATH == PLACEHOLDER_PATH
      UI.messagebox("UC Needs Modelling: set JSON_PATH at the top of this script to the floor's needs_modelling.json, "                     "then paste the script again. Nothing was loaded.")
      return false
    end
    unless File.file?(JSON_PATH)
      UI.messagebox("UC Needs Modelling: no such file\n#{JSON_PATH}\nSet JSON_PATH at the top of this script.")
      return false
    end
    doc = JSON.parse(File.read(JSON_PATH))
    unless doc['schema_version'] == 1
      UI.messagebox("UC Needs Modelling: schema_version #{doc['schema_version'].inspect} is not 1.")
      return false
    end
    @unit = doc['unit']
    @entries = doc['entries'] || []
    @index = -1 if @index >= @entries.size
    true
  end

  def self.ready?
    return true unless @entries.empty?
    return false unless load_entries
    if @entries.empty?
      UI.messagebox("UC Needs Modelling: #{@unit} has no spot that needs modelling.")
      return false
    end
    true
  end

  # The view's camera as it is now, kept once, before the first move; "Done" puts it back.
  def self.remember_camera(view)
    return unless @home_camera.nil?
    cam = view.camera
    @home_camera = [cam.eye, cam.target, cam.up, cam.perspective?, cam.fov]
  end

  def self.restore_camera
    return if @home_camera.nil?
    eye, target, up, perspective, fov = @home_camera
    cam = perspective ? Sketchup::Camera.new(eye, target, up, true, fov) : Sketchup::Camera.new(eye, target, up, false)
    model.active_view.camera = cam
    @home_camera = nil
  end

  def self.outside_model?(target)
    b = model.bounds
    return false unless b.valid?
    pad = FAR_OUTSIDE
    target.x < b.min.x - pad || target.x > b.max.x + pad ||
      target.y < b.min.y - pad || target.y > b.max.y + pad ||
      target.z < b.min.z - pad || target.z > b.max.z + pad
  end

  def self.describe(entry)
    area = entry['area_in2'].nil? ? 'no area' : format('%.0f sq in', entry['area_in2'])
    "#{entry['id']}  #{entry['kind']}  #{entry['reason']}  #{area}"
  end

  # Move the camera to entry `index` (wrapping round the list) and draw its outline.
  def self.go_to(index)
    return unless ready?
    @index = index % @entries.size
    entry = @entries[@index]
    view = model.active_view
    remember_camera(view)
    spot = entry['suggested_view']
    target = point(spot['target'])
    if outside_model?(target)
      UI.messagebox("UC Needs Modelling: spot #{entry['id']} lies far outside this model.\n" \
                    "Is this the file of #{@unit}? The camera was not moved.")
      return
    end
    up = Geom::Vector3d.new(spot['up'][0].to_f, spot['up'][1].to_f, spot['up'][2].to_f)
    view.camera = Sketchup::Camera.new(point(spot['eye']), target, up)
    show_outline
    Sketchup.status_text = "UC Needs Modelling #{@index + 1}/#{@entries.size}: #{describe(entry)}"
  end

  def self.show_outline
    return if @index < 0 || @entries.empty?
    entry = @entries[@index]
    points = (entry['border'] || []).map { |xyz| point(xyz) }
    model.select_tool(OutlineTool.new(points, entry['ordered'] ? true : false))
    model.active_view.invalidate
  end

  def self.next_spot
    return unless ready?
    go_to(@index + 1)
  end

  def self.previous_spot
    return unless ready?
    go_to(@index < 0 ? -1 : @index - 1)
  end

  # The list, in a dialog: one row per spot, "Go" moves the camera there.
  def self.list
    return unless ready?
    rows = @entries.each_with_index.map do |e, i|
      area = e['area_in2'].nil? ? '' : format('%.0f', e['area_in2'])
      "<tr><td><a href='#' onclick='sketchup.go(#{i}); return false'>Go</a></td><td>#{i + 1}</td><td>#{CGI.escapeHTML(e['id'].to_s)}</td>" \
        "<td>#{CGI.escapeHTML(e['kind'].to_s)}</td><td>#{CGI.escapeHTML(e['reason'].to_s)}</td><td>#{area}</td></tr>"
    end
    html = "<html><body style='font-family:sans-serif;font-size:13px'><h3>#{CGI.escapeHTML(@unit.to_s)}: " \
           "#{@entries.size} spots to model</h3><table cellpadding='3'><tr><th></th><th>#</th><th>id</th>" \
           "<th>kind</th><th>reason</th><th>area sq in</th></tr>#{rows.join}</table></body></html>"
    if @dialog.nil?
      @dialog = UI::HtmlDialog.new(dialog_title: "#{MENU_TITLE}: list", width: 560, height: 600, resizable: true)
      @dialog.add_action_callback('go') { |_context, i| go_to(i.to_i) }
      @dialog.set_on_closed { @dialog = nil }
    end
    @dialog.set_html(html)
    @dialog.show
  end

  # Put the camera back, stop drawing the outline and forget the list (the dialog, if open, is only told it is done).
  def self.done
    restore_camera
    model.select_tool(nil)
    @dialog.set_html("<html><body style='font-family:sans-serif'>Done. You can close this window.</body></html>") if @dialog
    @entries = []
    @index = -1
    Sketchup.status_text = ''
  end

  def self.install_menu
    return if @menu_ready
    menu = UI.menu('Extensions').add_submenu(MENU_TITLE)
    menu.add_item('Next spot') { next_spot }
    menu.add_item('Previous spot') { previous_spot }
    menu.add_item('Show outline again') { show_outline }
    menu.add_item('List') { list }
    menu.add_item('Done') { done }
    @menu_ready = true
  end

  install_menu
  puts(load_entries ? "UC Needs Modelling: #{@entries.size} spots of #{@unit}; use Extensions > #{MENU_TITLE}" : 'UC Needs Modelling: nothing loaded')
end
