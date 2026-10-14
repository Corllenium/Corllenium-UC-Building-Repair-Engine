// Imports one staged OBJ under the project's postprocessors (the owner's CampusModelImporter copy, then
// UcImportOverrides) and writes what Unity made of it: <name>.obj, <name>.mtl, then <name>.unity.json LAST.
// Never saves a scene. Exits 0 on success, 1 on any exception.
using System;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

public static class UcFloorExport
{
    static string Arg(string key)
    {
        var a = Environment.GetCommandLineArgs();
        int i = Array.IndexOf(a, key);
        return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
    }

    public static void ExportFromCli()
    {
        try
        {
            string asset = Arg("-ucAsset"), outDir = Arg("-ucOut"), name = Arg("-ucName");
            AssetDatabase.ImportAsset(asset, ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);
            var root = AssetDatabase.LoadAssetAtPath<GameObject>(asset);
            if (root == null) throw new Exception("Unity imported nothing at " + asset);
            Directory.CreateDirectory(outDir);
            Write(root, (ModelImporter)AssetImporter.GetAtPath(asset), asset, outDir, name);
            EditorApplication.Exit(0);
        }
        catch (Exception e)
        {
            Debug.LogError("UcFloorExport failed: " + e);
            EditorApplication.Exit(1);
        }
    }

    static string F(float x) => x.ToString("R", CultureInfo.InvariantCulture);

    static void Write(GameObject root, ModelImporter imp, string asset, string outDir, string name)
    {
        var obj = new StringBuilder($"mtllib {name}.mtl\n");
        var mtl = new StringBuilder();
        var seen = new System.Collections.Generic.HashSet<string>();
        var meshes = new StringBuilder();
        int vBase = 1;
        foreach (var mf in root.GetComponentsInChildren<MeshFilter>(true))
        {
            var mesh = mf.sharedMesh;
            var mr = mf.GetComponent<MeshRenderer>();
            var rel = root.transform.worldToLocalMatrix * mf.transform.localToWorldMatrix;
            var nrel = rel.inverse.transpose;
            obj.Append($"o {mesh.name}\n");
            foreach (var v in mesh.vertices) { var p = rel.MultiplyPoint3x4(v); obj.Append($"v {F(p.x)} {F(p.y)} {F(p.z)}\n"); }
            var uv = mesh.uv;
            for (int i = 0; i < mesh.vertexCount; i++) { var t = i < uv.Length ? uv[i] : Vector2.zero; obj.Append($"vt {F(t.x)} {F(t.y)}\n"); }
            foreach (var n in mesh.normals) { var q = nrel.MultiplyVector(n).normalized; obj.Append($"vn {F(q.x)} {F(q.y)} {F(q.z)}\n"); }
            var subs = new StringBuilder();
            for (int s = 0; s < mesh.subMeshCount; s++)
            {
                var mat = mr != null && s < mr.sharedMaterials.Length ? mr.sharedMaterials[s] : null;
                string mname = mat != null ? mat.name : "<none>";
                string tex = mat != null && mat.mainTexture != null ? Path.GetFileName(AssetDatabase.GetAssetPath(mat.mainTexture)) : null;
                if (seen.Add(mname)) { mtl.Append($"newmtl {mname}\n"); if (tex != null) mtl.Append($"map_Kd {tex}\n"); }
                obj.Append($"usemtl {mname}\n");
                var tri = mesh.GetTriangles(s);
                for (int k = 0; k < tri.Length; k += 3)
                {
                    int a = tri[k] + vBase, b = tri[k + 1] + vBase, c = tri[k + 2] + vBase;
                    obj.Append($"f {a}/{a}/{a} {b}/{b}/{b} {c}/{c}/{c}\n");
                }
                if (subs.Length > 0) subs.Append(',');
                subs.Append($"{{\"material\":{Json(mname)},\"texture\":{(tex == null ? "null" : Json(tex))},\"triangle_count\":{tri.Length / 3}}}");
            }
            vBase += mesh.vertexCount;
            if (meshes.Length > 0) meshes.Append(',');
            meshes.Append($"{{\"name\":{Json(mesh.name)},\"vertex_count\":{mesh.vertexCount},\"index_format\":\"{mesh.indexFormat}\",\"submeshes\":[{subs}]}}");
        }
        File.WriteAllText(Path.Combine(outDir, name + ".obj"), obj.ToString());
        File.WriteAllText(Path.Combine(outDir, name + ".mtl"), mtl.ToString());
        string owner = File.ReadAllText(Path.Combine(Application.dataPath, "Editor", "CampusModelImporter.cs"));
        string sha;
        using (var h = SHA256.Create()) sha = string.Concat(h.ComputeHash(Encoding.UTF8.GetBytes(owner)).Select(x => x.ToString("x2")));
        string ov = File.Exists("overrides.json") ? File.ReadAllText("overrides.json") : "{}";
        var side = "{\"schema\":1,\"complete\":true,\"unity_version\":" + Json(Application.unityVersion) +
                   ",\"asset_path\":" + Json(asset) +
                   ",\"importer\":{\"globalScale\":" + F(imp.globalScale) + ",\"useFileUnits\":" + (imp.useFileUnits ? "true" : "false") +
                   ",\"weldVertices\":" + (imp.weldVertices ? "true" : "false") + ",\"importNormals\":" + Json(imp.importNormals.ToString()) +
                   ",\"normalSmoothingAngle\":" + F(imp.normalSmoothingAngle) + ",\"meshCompression\":" + Json(imp.meshCompression.ToString()) +
                   ",\"indexFormat\":" + Json(imp.indexFormat.ToString()) + ",\"generateSecondaryUV\":" + (imp.generateSecondaryUV ? "true" : "false") +
                   ",\"isReadable\":" + (imp.isReadable ? "true" : "false") + "}" +
                   ",\"importer_sha256\":" + Json(sha) + ",\"overrides\":" + ov + ",\"meshes\":[" + meshes + "]}";
        File.WriteAllText(Path.Combine(outDir, name + ".unity.json"), side);   // LAST: marks the dump complete
    }

    static string Json(string s) => "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
}
