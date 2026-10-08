# Isolated CD-F2 OpenKarto trace insertion

The production source and binary were not modified. In an isolated copy of
`nav2d_karto/OpenKarto/source/OpenMapper.cpp`, add `<cstdlib>`, `<iomanip>`, and
`<limits>` to the existing includes. In `ScanMatcher::CorrelateScan`, insert the
following immediately after the existing `rMean = averagePose;` assignment.
The original source uses CRLF; a copied source can be normalized to LF first.

```cpp
// CD-F2 isolated forensic build only; read-only trace after matching.
const char* f2TracePath = std::getenv("ACSLAM_F2_TRACE_PATH");
const Pose2 f2Odom = pScan->GetOdometricPose();
if (f2TracePath != NULL && f2Odom.GetX() > 5.078 && f2Odom.GetX() < 5.080)
{
  kt_int32s f2BestIndex = -1;
  kt_int32s f2SecondIndex = -1;
  kt_double f2SecondResponse = -1;
  kt_int32s f2TieCount = 0;
  for (kt_int32u i = 0; i < poseResponseSize; i++)
  {
    if (math::DoubleEqual(poseResponses[i].first, bestResponse))
    {
      f2TieCount++;
      if (f2BestIndex < 0) f2BestIndex = static_cast<kt_int32s>(i);
    }
    else if (poseResponses[i].first > f2SecondResponse)
    {
      f2SecondResponse = poseResponses[i].first;
      f2SecondIndex = static_cast<kt_int32s>(i);
    }
  }
  std::ofstream f2Trace(f2TracePath, std::ios::app);
  if (f2Trace.is_open())
  {
    f2Trace << std::setprecision(std::numeric_limits<kt_double>::max_digits10);
    f2Trace << "{\"stage\":\"" << (doingFineMatch ? "fine" : "coarse")
            << "\",\"odom_x\":" << f2Odom.GetX()
            << ",\"odom_y\":" << f2Odom.GetY()
            << ",\"search_center\":[" << rSearchCenter.GetX() << ","
            << rSearchCenter.GetY() << "," << rSearchCenter.GetHeading() << "]"
            << ",\"search_resolution\":[" << rSearchSpaceResolution.GetX()
            << "," << rSearchSpaceResolution.GetY() << "]"
            << ",\"best_response\":" << bestResponse
            << ",\"second_response\":" << f2SecondResponse
            << ",\"tie_count\":" << f2TieCount
            << ",\"best_index\":" << f2BestIndex
            << ",\"second_index\":" << f2SecondIndex
            << ",\"selected_mean\":[" << rMean.GetX() << "," << rMean.GetY()
            << "," << rMean.GetHeading() << "]"
            << ",\"covariance\":[[" << rCovariance(0,0) << ","
            << rCovariance(0,1) << "," << rCovariance(0,2) << "],["
            << rCovariance(1,0) << "," << rCovariance(1,1) << ","
            << rCovariance(1,2) << "],[" << rCovariance(2,0) << ","
            << rCovariance(2,1) << "," << rCovariance(2,2) << "]]}\n";
  }
}
```

The isolated build used `/usr/bin/python3` 3.8, `CMAKE_BUILD_TYPE=Release`,
and the frozen generated message headers from the production workspace.
The observed isolated source SHA-256 was
`fc1e7b1b10abc64eea51deaf7311d189e7e803f8df566aece6220b631337e459`;
the binary SHA-256 was
`3ea511fb6c5b94fefb2dd8aa9088dda52a3c0d957508e9fad0ec037263506e82`.
Because the copied source retained mixed original/edited line endings, the
snippet reproduces the observation logic, not byte-identical source or binary.
