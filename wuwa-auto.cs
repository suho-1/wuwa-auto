using System;
using System.Diagnostics;
using System.IO;

namespace WuwaAutoLauncher
{
    class Program
    {
        static int Main(string[] args)
        {
            Console.Title = "wuwa-auto";
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;

            string workingDir = File.Exists(Path.Combine(baseDir, "main.py"))
                ? baseDir
                : (Directory.Exists(Path.Combine(baseDir, @"data\apps\ok-ww\working"))
                    ? Path.Combine(baseDir, @"data\apps\ok-ww\working")
                    : baseDir);

            string mainPy = Path.Combine(workingDir, "main.py");

            string pyExe;
            if (File.Exists(Path.Combine(baseDir, @"data\apps\ok-ww\python\python.exe")))
            {
                pyExe = Path.Combine(baseDir, @"data\apps\ok-ww\python\python.exe");
            }
            else if (File.Exists(Path.Combine(workingDir, @"..\python\python.exe")))
            {
                pyExe = Path.GetFullPath(Path.Combine(workingDir, @"..\python\python.exe"));
            }
            else
            {
                pyExe = "python.exe";
            }

            if (!File.Exists(pyExe) && pyExe != "python.exe")
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("Error: Python executable not found at: " + pyExe);
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
                return 1;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pyExe;
            psi.Arguments = "\"" + mainPy + "\"";
            psi.WorkingDirectory = workingDir;
            psi.UseShellExecute = false;

            try
            {
                using (Process proc = Process.Start(psi))
                {
                    proc.WaitForExit();
                    return proc.ExitCode;
                }
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("Error launching wuwa-auto: " + ex.Message);
                Console.ResetColor();
                Console.WriteLine("\nPress any key to exit...");
                Console.ReadKey();
                return 1;
            }
        }
    }
}
