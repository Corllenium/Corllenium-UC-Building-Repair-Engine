// MIRROR-ONLY. Runs AFTER the owner's CampusModelImporter (higher postprocess order) and applies
// overrides.json (one setting at a time, for the cause hunt). With {} it changes nothing.
using System.IO;
using UnityEditor;
using UnityEngine;

public class UcImportOverrides : AssetPostprocessor
{
    public override int GetPostprocessOrder() => 1000;

    void OnPreprocessModel()
    {
        var path = Path.Combine(Directory.GetCurrentDirectory(), "overrides.json");
        if (!File.Exists(path)) return;
        var o = JsonUtility.FromJson<Overrides>(File.ReadAllText(path));
        var imp = (ModelImporter)assetImporter;
        if (!string.IsNullOrEmpty(o.weldVertices)) imp.weldVertices = o.weldVertices == "true";
        if (!string.IsNullOrEmpty(o.importNormals))
            imp.importNormals = (ModelImporterNormals)System.Enum.Parse(typeof(ModelImporterNormals), o.importNormals);
        if (!string.IsNullOrEmpty(o.meshCompression))
            imp.meshCompression = (ModelImporterMeshCompression)System.Enum.Parse(typeof(ModelImporterMeshCompression), o.meshCompression);
        if (!string.IsNullOrEmpty(o.indexFormat))
            imp.indexFormat = (ModelImporterIndexFormat)System.Enum.Parse(typeof(ModelImporterIndexFormat), o.indexFormat);
        if (!string.IsNullOrEmpty(o.normalSmoothingAngle)) imp.normalSmoothingAngle = float.Parse(o.normalSmoothingAngle);
        if (!string.IsNullOrEmpty(o.generateSecondaryUV)) imp.generateSecondaryUV = o.generateSecondaryUV == "true";
    }

    [System.Serializable]
    class Overrides
    {
        public string weldVertices, importNormals, meshCompression, indexFormat, normalSmoothingAngle, generateSecondaryUV;
    }
}
