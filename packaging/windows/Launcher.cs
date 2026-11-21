using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class Launcher
{
    [STAThread]
    private static void Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string runtime = Path.Combine(root, "runtime");
        string setup = Path.Combine(root, "app", "setup_runtime.py");
        string ready = Path.Combine(runtime, "Lib", "site-packages", ".bili-cache-ready");
        bool install = File.Exists(setup) && !File.Exists(ready);
        string python = Path.Combine(runtime, install ? "python.exe" : "pythonw.exe");
        string app = install ? setup : Path.Combine(root, "app", "main.py");

        try
        {
            Process.Start(new ProcessStartInfo(python, "-B \"" + app + "\"")
            {
                UseShellExecute = false,
                WorkingDirectory = root
            });
        }
        catch (Exception error)
        {
            MessageBox.Show("Could not start Bilibili Cache. Extract the entire ZIP before running.\n\n"
                + error.Message, "Bilibili Cache", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
