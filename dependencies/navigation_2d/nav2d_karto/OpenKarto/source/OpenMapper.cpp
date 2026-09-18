/*
 * Copyright (C) 2006-2011, SRI International (R)
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Lesser General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#ifdef USE_TBB
#include <tbb/tbb_thread.h>
#include <tbb/concurrent_queue.h>
#endif

#include <stdexcept>
#include <queue>
#include <set>
#include <iterator>
#include <map>
#include <iostream>
#include <fstream>
#include <sstream>
#include <chrono>
#include <string>

#include <ros/ros.h>

#include <OpenKarto/OpenMapper.h>
#include <OpenKarto/Logger.h>

namespace karto
{

  // enable this for verbose debug information
  //#define KARTO_DEBUG
  //#define KARTO_DEBUG2

  #define MAX_VARIANCE            500.0
  #define DISTANCE_PENALTY_GAIN   0.2
  #define ANGLE_PENALTY_GAIN      0.2

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  // Observation-only Phase 2C loop-closure diagnostics helpers.
  // These helpers never alter matching, candidate selection, chain construction,
  // thresholds, return values, optimization, or any SLAM decision. They only
  // serialize intermediate values that the original algorithm already computes.

  namespace
  {
    std::string LoopDiagDouble(kt_double value)
    {
      char buffer[64];
      snprintf(buffer, sizeof(buffer), "%.6f", value);
      return std::string(buffer);
    }

    std::string LoopDiagBool(kt_bool value)
    {
      return value ? "true" : "false";
    }

    const char* ConstraintProvenanceName(ConstraintCreationProvenance provenance)
    {
      switch (provenance)
      {
        case ConstraintProvenance_PreviousScan: return "PREVIOUS_SCAN";
        case ConstraintProvenance_RunningScanChain: return "RUNNING_SCAN_CHAIN";
        case ConstraintProvenance_NearChain: return "NEAR_CHAIN";
        case ConstraintProvenance_TryCloseLoop: return "TRY_CLOSE_LOOP";
        case ConstraintProvenance_FirstScanCrossSensor: return "FIRST_SCAN_CROSS_SENSOR";
        case ConstraintProvenance_CustomObjectLastScan: return "CUSTOM_OBJECT_LAST_SCAN";
        default: return "OTHER";
      }
    }

    std::string OptionalDiagDouble(kt_bool available, kt_double value)
    {
      return available ? LoopDiagDouble(value) : "null";
    }

    // JSON object fragment describing a candidate chain and its scan-index gap to
    // the current scan. Returns e.g.:
    //   "chain_size":4,"scan_ids":[12,13,14,15],"min_scan_index_gap":100,"max_scan_index_gap":103
    std::string LoopDiagChainFragment(const LocalizedLaserScanList& rChain, kt_int32s currentStateId)
    {
      std::ostringstream oss;
      oss << "\"chain_size\":" << rChain.Size() << ",\"scan_ids\":[";
      kt_int32s minGap = 0;
      kt_int32s maxGap = 0;
      bool first = true;
      bool hasGap = false;
      karto_const_forEach(LocalizedLaserScanList, &rChain)
      {
        if (!first)
        {
          oss << ",";
        }
        first = false;
        kt_int32s scanId = (*iter)->GetStateId();
        kt_int32s gap = currentStateId - scanId;
        if (!hasGap)
        {
          minGap = gap;
          maxGap = gap;
          hasGap = true;
        }
        else
        {
          if (gap < minGap) minGap = gap;
          if (gap > maxGap) maxGap = gap;
        }
        oss << scanId;
      }
      oss << "],\"min_scan_index_gap\":" << minGap
          << ",\"max_scan_index_gap\":" << maxGap;
      return oss.str();
    }

    // No-chain reject reason derived only from already-computed counts.
    std::string LoopDiagNoChainReason(kt_int32u inDistance, kt_int32u nearLinked)
    {
      if (inDistance == 0)
      {
        return "NO_SPATIAL_CANDIDATE";
      }
      if (inDistance - nearLinked == 0)
      {
        return "ALL_CANDIDATES_NEAR_LINKED";
      }
      return "CHAIN_TOO_SHORT";
    }
  }

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  /**
   * Manages the data for a sensor
   */
  class SensorDataManager
  {
  public:
    /**
     * Default constructor
     */
    SensorDataManager(kt_int32u runningBufferMaximumSize, kt_double runningBufferMaximumDistance)
      : m_pLastScan(NULL)
      , m_RunningBufferMaximumSize(runningBufferMaximumSize)
      , m_RunningBufferMaximumDistance(runningBufferMaximumDistance)
    {
    }

    /**
     * Destructor
     */
    virtual ~SensorDataManager()
    {
      Clear();
    }

  public:
    /**
     * Adds objects to list of objects, tagging object with given unique id;
     * if object is a scan, then scan gets added to list of processed scans
     * @param pObject object
     * @param uniqueId unique id
     */
    inline void AddObject(LocalizedObject* pObject, kt_int32s uniqueId)
    {
      // assign state id to object
      pObject->SetStateId(static_cast<kt_int32u>(m_Objects.Size()));

      // assign unique id to object
      pObject->SetUniqueId(uniqueId);

      m_Objects.Add(pObject);
      
      // if object is scan and it was scan-matched, add it to scan buffer
      LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
      if (pScan != NULL)
      {
        m_Scans.Add(pScan);
      }      
    }

    /**
     * Gets last scan
     * @return last localized scan
     */
    inline LocalizedLaserScan* GetLastScan()
    {
      return m_pLastScan;
    }

    /**
     * Sets the last scan
     * @param pScan
     */
    inline void SetLastScan(LocalizedLaserScan* pScan)
    {
      m_pLastScan = pScan;
    }

    /**
     * Gets objects
     * @return objects
     */
    inline LocalizedObjectList& GetObjects()
    {
      return m_Objects;
    }
    
    /**
     * Gets scans
     * @return scans
     */
    inline LocalizedLaserScanList& GetScans()
    {
      return m_Scans;
    }
    
    /**
     * Gets index of scan in sensor's list of scans
     * @param pScan
     * @return index into scans list; -1 if not found
     */
    inline kt_int32s GetScanIndex(LocalizedLaserScan* pScan)
    {
      LocalizedLaserScanPtr pSmartScan(pScan);
      return m_Scans.BinarySearch(pSmartScan, ScanIndexComparator);
    }

    /**
     * Gets running scans
     * @return running scans
     */
    inline LocalizedLaserScanList& GetRunningScans()
    {
      return m_RunningScans;
    }

    /**
     * Adds scan to list of running scans
     * @param pScan
     */
    void AddRunningScan(LocalizedLaserScan* pScan)
    {
      m_RunningScans.Add(pScan);

      // list has at least one element (first line of this function), so this is valid
      Pose2 frontScanPose = m_RunningScans.Front()->GetSensorPose();
      Pose2 backScanPose = m_RunningScans.Back()->GetSensorPose();

      // cap list size and remove all scans from front of list that are too far from end of list
      kt_double squaredDistance = frontScanPose.GetPosition().SquaredDistance(backScanPose.GetPosition());
      while (m_RunningScans.Size() > m_RunningBufferMaximumSize || squaredDistance > math::Square(m_RunningBufferMaximumDistance) - KT_TOLERANCE)
      {
        // remove front of running scans
        m_RunningScans.Remove(m_RunningScans.Front());

        // recompute stats of running scans
        frontScanPose = m_RunningScans.Front()->GetSensorPose();
        backScanPose = m_RunningScans.Back()->GetSensorPose();
        squaredDistance = frontScanPose.GetPosition().SquaredDistance(backScanPose.GetPosition());
      }
    }

    /**
     * Deletes data of this buffered sensor
     */
    void Clear()
    {
      m_Objects.Clear();
      m_Scans.Clear();
      m_RunningScans.Clear();
      m_pLastScan = NULL;
    }

  private:
    static kt_int32s ScanIndexComparator(const LocalizedLaserScanPtr& pScan1, const LocalizedLaserScanPtr& pScan2)
    {
      return pScan1->GetStateId() - pScan2->GetStateId();
    }
    
  private:
    LocalizedObjectList m_Objects;
    
    LocalizedLaserScanList m_Scans;
    LocalizedLaserScanList m_RunningScans;
    LocalizedLaserScanPtr m_pLastScan;

    kt_int32u m_RunningBufferMaximumSize;
    kt_double m_RunningBufferMaximumDistance;
  }; // SensorDataManager

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  typedef std::map<Identifier, SensorDataManager*> SensorDataManagerMap;

  struct MapperSensorManagerPrivate
  {
    // map from sensor name to sensor data
    SensorDataManagerMap m_SensorDataManagers;
    
    kt_int32u m_RunningBufferMaximumSize;
    kt_double m_RunningBufferMaximumDistance;
    
    kt_int32s m_NextUniqueId;    
    
    LocalizedObjectList m_Objects;
  };

  MapperSensorManager::MapperSensorManager(kt_int32u runningBufferMaximumSize, kt_double runningBufferMaximumDistance)
    : m_pMapperSensorManagerPrivate(new MapperSensorManagerPrivate())
  {
    m_pMapperSensorManagerPrivate->m_RunningBufferMaximumSize = runningBufferMaximumSize;
    m_pMapperSensorManagerPrivate->m_RunningBufferMaximumDistance = runningBufferMaximumDistance;
    m_pMapperSensorManagerPrivate->m_NextUniqueId = 0;
  }
  
  MapperSensorManager::~MapperSensorManager()
  {
    Clear();
    delete m_pMapperSensorManagerPrivate;
  }
  
  
  void MapperSensorManager::RegisterSensor(const Identifier& rSensorName)
  {
    if (GetSensorDataManager(rSensorName) == NULL)
    {
      m_pMapperSensorManagerPrivate->m_SensorDataManagers[rSensorName] = new SensorDataManager(m_pMapperSensorManagerPrivate->m_RunningBufferMaximumSize, m_pMapperSensorManagerPrivate->m_RunningBufferMaximumDistance);
    }
  }

  LocalizedObject* MapperSensorManager::GetLocalizedObject(const Identifier& rSensorName, kt_int32s stateId)
  {
    SensorDataManager* pSensorDataManager = GetSensorDataManager(rSensorName);
    if (pSensorDataManager != NULL)
    {
      return pSensorDataManager->GetObjects().Get(stateId);
    }

    assert(false);
    return NULL;
  }
  
  // for use by scan solver
  LocalizedObject* MapperSensorManager::GetLocalizedObject(kt_int32s uniqueId)
  {
    assert(math::IsUpTo(uniqueId, (kt_int32s)m_pMapperSensorManagerPrivate->m_Objects.Size()));
    return m_pMapperSensorManagerPrivate->m_Objects[uniqueId];
  }
  
  List<Identifier> MapperSensorManager::GetSensorNames()
  {
    List<Identifier> sensorNames;
    const_forEach(SensorDataManagerMap, &m_pMapperSensorManagerPrivate->m_SensorDataManagers)
    {
      sensorNames.Add(iter->first);
    }
    
    return sensorNames;
  }
  
  LocalizedLaserScan* MapperSensorManager::GetLastScan(const Identifier& rSensorName)
  {
    return GetSensorDataManager(rSensorName)->GetLastScan();
  }
  
  void MapperSensorManager::SetLastScan(LocalizedLaserScan* pScan)
  {
    GetSensorDataManager(pScan)->SetLastScan(pScan);
  }
  
  void MapperSensorManager::ClearLastScan(const Identifier& rSensorName)
  {
    GetSensorDataManager(rSensorName)->SetLastScan(NULL);
  }

  void MapperSensorManager::AddLocalizedObject(LocalizedObject* pObject)
  {
    GetSensorDataManager(pObject)->AddObject(pObject, m_pMapperSensorManagerPrivate->m_NextUniqueId);
    m_pMapperSensorManagerPrivate->m_Objects.Add(pObject);
    m_pMapperSensorManagerPrivate->m_NextUniqueId++;
  }
  
  void MapperSensorManager::AddRunningScan(LocalizedLaserScan* pScan)
  {
    GetSensorDataManager(pScan)->AddRunningScan(pScan);
  }
  
  LocalizedLaserScanList& MapperSensorManager::GetScans(const Identifier& rSensorName)
  {
    return GetSensorDataManager(rSensorName)->GetScans();
  }
  
  kt_int32s MapperSensorManager::GetScanIndex(LocalizedLaserScan* pScan)
  {
    return GetSensorDataManager(pScan->GetSensorIdentifier())->GetScanIndex(pScan);
  }

  LocalizedLaserScanList& MapperSensorManager::GetRunningScans(const Identifier& rSensorName)
  {
    return GetSensorDataManager(rSensorName)->GetRunningScans();
  }
  
  LocalizedLaserScanList MapperSensorManager::GetAllScans()
  {
    LocalizedLaserScanList scans;
    
    forEach(SensorDataManagerMap, &m_pMapperSensorManagerPrivate->m_SensorDataManagers)
    {
      LocalizedLaserScanList& rScans = iter->second->GetScans();
      scans.Add(rScans);
    }
    
    return scans;
  }

  karto::LocalizedObjectList MapperSensorManager::GetAllObjects()
  {
    LocalizedObjectList objects;

    forEach(SensorDataManagerMap, &m_pMapperSensorManagerPrivate->m_SensorDataManagers)
    {
      LocalizedObjectList& rObjects = iter->second->GetObjects();
      objects.Add(rObjects);
    }

    return objects;
  }

  void MapperSensorManager::Clear()
  {
    forEach(SensorDataManagerMap, &m_pMapperSensorManagerPrivate->m_SensorDataManagers)
    {
      delete iter->second;
    }
    
    m_pMapperSensorManagerPrivate->m_SensorDataManagers.clear();
  }
  
  SensorDataManager* MapperSensorManager::GetSensorDataManager(const Identifier& rSensorName)
  {
    if (m_pMapperSensorManagerPrivate->m_SensorDataManagers.find(rSensorName) != m_pMapperSensorManagerPrivate->m_SensorDataManagers.end())
    {
      return m_pMapperSensorManagerPrivate->m_SensorDataManagers[rSensorName];
    }
    
    return NULL;
  }  

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
   
#ifdef USE_TBB
  class ScanMatcherGridSetBank
  {
  public:
    ScanMatcherGridSetBank(kt_int32u nGrids, kt_int32s corrGridWidth, kt_int32s corrGridHeight, kt_double resolution, kt_double smearDeviation,
                        kt_int32s searchSpaceGridWidth, kt_int32s searchSpaceGridHeight)
    {
      if (nGrids <= 0)
      {
        throw Exception("ScanMatcherGridSetBank requires at least 1 grid: " + StringHelper::ToString(nGrids));
        assert(false);
      }
           
      for (kt_int32u i = 0; i < nGrids; i++)
      {
        CorrelationGrid* pCorrelationGrid = CorrelationGrid::CreateGrid(corrGridWidth, corrGridHeight, resolution, smearDeviation);
        Grid<kt_double>* pSearchSpaceProbs = Grid<kt_double>::CreateGrid(searchSpaceGridWidth, searchSpaceGridHeight, resolution);
        GridIndexLookup<kt_int8u>* pGridLookup = new GridIndexLookup<kt_int8u>(pCorrelationGrid);
        
        m_ScanMatcherGridSets.push(new ScanMatcherGridSet(pCorrelationGrid, pSearchSpaceProbs, pGridLookup));
      }
    }
    
    virtual ~ScanMatcherGridSetBank()
    {
      // we add a NULL item on the queue in case we are stuck in CheckOut!
      m_ScanMatcherGridSets.push(NULL);

      m_ScanMatcherGridSets.clear();
    }
    
  public:
    /**
     * If no ScanMatcherGridSet on queue this thread will wait until one becomes available!
     */
    SmartPointer<ScanMatcherGridSet> CheckOut()
    {
      SmartPointer<ScanMatcherGridSet> pScanMatcherGridSet = NULL;

      m_ScanMatcherGridSets.pop(pScanMatcherGridSet);
      
      return pScanMatcherGridSet;
    }
    
    /**
     * Return ScanMatcherGridSet to queue
     */
    void Return(SmartPointer<ScanMatcherGridSet> pScanMatcherGridSet)
    {
      m_ScanMatcherGridSets.push(pScanMatcherGridSet);
    }
    
  private:
    tbb::concurrent_bounded_queue<SmartPointer<ScanMatcherGridSet> > m_ScanMatcherGridSets;    
  };
#else
  class ScanMatcherGridSetBank
  {
  };
#endif
  
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////  
  
  ScanMatcher::~ScanMatcher()
  {
    delete m_pScanMatcherGridSetBank;
  }
  
  ScanMatcher* ScanMatcher::Create(OpenMapper* pOpenMapper, kt_double searchSize, kt_double resolution, kt_double smearDeviation, kt_double rangeThreshold)
  {
    // invalid parameters
    if (resolution <= 0)
    {
      return NULL;
    }
    if (searchSize <= 0)
    {
      return NULL;
    }
    if (smearDeviation < 0)
    {
      return NULL;
    }
    if (rangeThreshold <= 0)
    {
      return NULL;
    }
    
    assert(math::DoubleEqual(math::Round(searchSize / resolution), (searchSize / resolution)));
    
    // calculate search space in grid coordinates
    kt_int32u searchSpaceSideSize = static_cast<kt_int32u>(math::Round(searchSize / resolution) + 1);
    
    // compute requisite size of correlation grid (pad grid so that scan points can't fall off the grid
    // if a scan is on the border of the search space)
    kt_int32u pointReadingMargin = static_cast<kt_int32u>(ceil(rangeThreshold / resolution));
    
    kt_int32s gridSize = searchSpaceSideSize + 2 * pointReadingMargin;
    
    // create correlation grid
    assert(gridSize % 2 == 1);
    CorrelationGrid* pCorrelationGrid = CorrelationGrid::CreateGrid(gridSize, gridSize, resolution, smearDeviation);

    // create search space probabilities
    Grid<kt_double>* pSearchSpaceProbs = Grid<kt_double>::CreateGrid(searchSpaceSideSize, searchSpaceSideSize, resolution);
    
    GridIndexLookup<kt_int8u>* pGridLookup = new GridIndexLookup<kt_int8u>(pCorrelationGrid);
    
    ScanMatcher* pScanMatcher = new ScanMatcher(pOpenMapper);
    pScanMatcher->m_pScanMatcherGridSet = new ScanMatcherGridSet(pCorrelationGrid, pSearchSpaceProbs, pGridLookup);
    
    if (pOpenMapper->IsMultiThreaded())
    {
#ifdef USE_TBB
      pScanMatcher->m_pScanMatcherGridSetBank = new ScanMatcherGridSetBank(10, gridSize, gridSize, resolution, smearDeviation, searchSpaceSideSize, searchSpaceSideSize);                                                                         
#else
      pScanMatcher->m_pScanMatcherGridSetBank = NULL;
#endif
    }

    return pScanMatcher;
  }
  
  kt_double ScanMatcher::MatchScan(LocalizedLaserScan* pScan, const LocalizedLaserScanList& rBaseScans, Pose2& rMean, Matrix3& rCovariance, kt_bool doPenalize, kt_bool doRefineMatch)
  {
    SmartPointer<ScanMatcherGridSet> pScanMatcherGridSet;

    if (m_pOpenMapper->IsMultiThreaded())
    {
#ifdef USE_TBB
      pScanMatcherGridSet = m_pScanMatcherGridSetBank->CheckOut();
#else
      pScanMatcherGridSet = m_pScanMatcherGridSet;
#endif
    }
    else
    {
      pScanMatcherGridSet = m_pScanMatcherGridSet;
    }

    CorrelationGrid* pCorrelationGrid = pScanMatcherGridSet->m_pCorrelationGrid;
    Grid<kt_double>* pSearchSpaceProbs = pScanMatcherGridSet->m_pSearchSpaceProbs;
    
    ///////////////////////////////////////
    // set scan pose to be center of grid
    
    // 1. get scan position
    Pose2 scanPose = pScan->GetSensorPose();
    
    // scan has no readings; cannot do scan matching
    // best guess of pose is based off of adjusted odometer reading
    if (pScan->GetPointReadings(true).Size() == 0)
    {
      rMean = scanPose;
      
      // maximum covariance
      rCovariance(0, 0) = MAX_VARIANCE; // XX
      rCovariance(1, 1) = MAX_VARIANCE; // YY
      rCovariance(2, 2) = 4 * math::Square(m_pOpenMapper->m_pCoarseAngleResolution->GetValue()); // TH*TH
      
      if (m_pOpenMapper->IsMultiThreaded())
      {
#ifdef USE_TBB
        m_pScanMatcherGridSetBank->Return(pScanMatcherGridSet);
#endif
      }

      return 0.0;
    }
    
    // 2. get size of grid
    Rectangle2<kt_int32s> roi = pCorrelationGrid->GetROI();
    
    // 3. compute offset (in meters - lower left corner)
    Vector2d offset;
    offset.SetX(scanPose.GetX() - (0.5 * (roi.GetWidth() - 1) * pCorrelationGrid->GetResolution()));
    offset.SetY(scanPose.GetY() - (0.5 * (roi.GetHeight() - 1) * pCorrelationGrid->GetResolution()));
    
    // 4. set offset
    pCorrelationGrid->GetCoordinateConverter()->SetOffset(offset);
    
    ///////////////////////////////////////
    
    // set up correlation grid
    AddScansNew(pCorrelationGrid, rBaseScans, scanPose.GetPosition());
    
    // compute how far to search in each direction
    Vector2d searchDimensions(pSearchSpaceProbs->GetWidth(), pSearchSpaceProbs->GetHeight());
    Vector2d coarseSearchOffset(0.5 * (searchDimensions.GetX() - 1) * pCorrelationGrid->GetResolution(), 0.5 * (searchDimensions.GetY() - 1) * pCorrelationGrid->GetResolution());
    
    // a coarse search only checks half the cells in each dimension
    Vector2d coarseSearchResolution(2 * pCorrelationGrid->GetResolution(), 2 * pCorrelationGrid->GetResolution());
    
    // actual scan-matching
    kt_double bestResponse = CorrelateScan(pScanMatcherGridSet, pScan, scanPose,	coarseSearchOffset, coarseSearchResolution, m_pOpenMapper->m_pCoarseSearchAngleOffset->GetValue(), m_pOpenMapper->m_pCoarseAngleResolution->GetValue(), doPenalize, rMean, rCovariance, false);
    
    if (m_pOpenMapper->m_pUseResponseExpansion->GetValue() == true)
    {
      if (math::DoubleEqual(bestResponse, 0.0))
      {
#ifdef KARTO_DEBUG
        std::cout << "Mapper Info: Expanding response search space!" << std::endl;
#endif
        // try and increase search angle offset with 20 degrees and do another match
        kt_double newSearchAngleOffset = m_pOpenMapper->m_pCoarseSearchAngleOffset->GetValue();
        for (kt_int32u i = 0; i < 3; i++)
        {
          newSearchAngleOffset += math::DegreesToRadians(20);
          
          bestResponse = CorrelateScan(pScanMatcherGridSet, pScan, scanPose,	coarseSearchOffset, coarseSearchResolution, newSearchAngleOffset, m_pOpenMapper->m_pCoarseAngleResolution->GetValue(), doPenalize, rMean, rCovariance, false);
          
          if (math::DoubleEqual(bestResponse, 0.0) == false)
          {
            break;
          }
        }
        
#ifdef KARTO_DEBUG
        if (math::DoubleEqual(bestResponse, 0.0))
        {
          std::cout << "Mapper Warning: Unable to calculate response!" << std::endl;
        }
#endif
      }
    }
    
    if (doRefineMatch)
    {
      Vector2d fineSearchOffset(coarseSearchResolution * 0.5);
      Vector2d fineSearchResolution(pCorrelationGrid->GetResolution(), pCorrelationGrid->GetResolution());
      bestResponse = CorrelateScan(pScanMatcherGridSet, pScan, rMean, fineSearchOffset, fineSearchResolution, 0.5 * m_pOpenMapper->m_pCoarseAngleResolution->GetValue(), m_pOpenMapper->m_pFineSearchAngleOffset->GetValue(), doPenalize, rMean, rCovariance, true);
    }
    
#ifdef KARTO_DEBUG
    std::cout << "  BEST POSE = " << rMean << " BEST RESPONSE = " << bestResponse << ",  VARIANCE = " << rCovariance(0, 0) << ", " << rCovariance(1, 1) << std::endl;
#endif
    
    assert(math::InRange(rMean.GetHeading(), -KT_PI, KT_PI));

    if (m_pOpenMapper->IsMultiThreaded())
    {
#ifdef USE_TBB
      m_pScanMatcherGridSetBank->Return(pScanMatcherGridSet);
#endif
    }
    
    return bestResponse;
  }
  
#ifdef USE_TBB
  class Parallel_CorrelateScan
  {
  public:
    Parallel_CorrelateScan(std::vector<kt_double>* pNewPositionsY, std::vector<kt_double>* pSquaresY,
                           std::vector<kt_double>* pNewPositionsX, std::vector<kt_double>* pSquaresX,
                           std::vector<kt_double>* pAngles,
                           std::vector<std::pair<kt_double, Pose2> >* pPoseResponses,
                           ScanMatcher* pScanMatcher, kt_bool doPenalize,
                           kt_double distanceVariancePenalty, kt_double minimumDistancePenalty,
                           kt_double angleVariancePenalty, kt_double minimumAnglePenalty,
                           kt_double searchCenterHeading, ScanMatcherGridSet* pScanMatcherGridSet)
      : m_pNewPositionsY(pNewPositionsY)
      , m_pSquaresY(pSquaresY)
      , m_pNewPositionsX(pNewPositionsX)
      , m_pSquaresX(pSquaresX)
      , m_pAngles(pAngles)
      , m_pPoseResponses(pPoseResponses)
      , m_pScanMatcher(pScanMatcher)
      , m_DoPenalize(doPenalize)
      , m_DistanceVariancePenalty(distanceVariancePenalty)
      , m_MinimumDistancePenalty(minimumDistancePenalty)
      , m_AngleVariancePenalty(angleVariancePenalty)
      , m_MinimumAnglePenalty(minimumAnglePenalty)
      , m_SearchCenterHeading(searchCenterHeading)
      , m_pScanMatcherGridSet(pScanMatcherGridSet)
    {
      m_nX = pNewPositionsX->size();
      m_nAngles = pAngles->size();
    }
          
    void operator()(const tbb::blocked_range3d<kt_int32s, kt_int32s, kt_int32s>& rRange) const
    {      
      CorrelationGrid* pCorrelationGrid = m_pScanMatcherGridSet->m_pCorrelationGrid;
      
      for (tbb::blocked_range<kt_int32s>::const_iterator yIndex = rRange.pages().begin(); yIndex != rRange.pages().end(); yIndex++)
      {
        kt_double newPositionY = m_pNewPositionsY->at(yIndex);
        kt_double squareY = m_pSquaresY->at(yIndex);

        for (tbb::blocked_range<kt_int32s>::const_iterator xIndex = rRange.rows().begin(); xIndex != rRange.rows().end(); xIndex++)
        {
          kt_double newPositionX = m_pNewPositionsX->at(xIndex);
          kt_double squareX = m_pSquaresX->at(xIndex);

          Vector2i gridPoint = pCorrelationGrid->WorldToGrid(Vector2d(newPositionX, newPositionY));
          kt_int32s gridIndex = pCorrelationGrid->GridIndex(gridPoint);
          assert(gridIndex >= 0);
          
          kt_double squaredDistance = squareX + squareY;
          
          for (tbb::blocked_range<kt_int32s>::const_iterator angleIndex = rRange.cols().begin(); angleIndex != rRange.cols().end(); angleIndex++)
          {
            kt_int32u poseResponseIndex = (m_nX * m_nAngles) * yIndex + m_nAngles * xIndex + angleIndex;
            
            kt_double angle = m_pAngles->at(angleIndex);
            
            kt_double response = m_pScanMatcher->GetResponse(m_pScanMatcherGridSet, angleIndex, gridIndex);
            if (m_DoPenalize && (math::DoubleEqual(response, 0.0) == false))
            {
              // simple model (approximate Gaussian) to take odometry into account
              
              kt_double distancePenalty = 1.0 - (DISTANCE_PENALTY_GAIN * squaredDistance / m_DistanceVariancePenalty);
              distancePenalty = math::Maximum(distancePenalty, m_MinimumDistancePenalty);
              
              kt_double squaredAngleDistance = math::Square(angle - m_SearchCenterHeading);
              kt_double anglePenalty = 1.0 - (ANGLE_PENALTY_GAIN * squaredAngleDistance / m_AngleVariancePenalty);
              anglePenalty = math::Maximum(anglePenalty, m_MinimumAnglePenalty);
              
              response *= (distancePenalty * anglePenalty);
            }
            
            // store response and pose
            m_pPoseResponses->at(poseResponseIndex) = std::pair<kt_double, Pose2>(response, Pose2(newPositionX, newPositionY, math::NormalizeAngle(angle)));
          }
        }
      }
    }
    
  private:
    std::vector<kt_double>* m_pNewPositionsY;
    std::vector<kt_double>* m_pSquaresY;
    std::vector<kt_double>* m_pNewPositionsX;
    std::vector<kt_double>* m_pSquaresX;
    std::vector<kt_double>* m_pAngles;
    std::vector<std::pair<kt_double, Pose2> >* m_pPoseResponses;
    ScanMatcher* m_pScanMatcher;
    kt_bool m_DoPenalize;
    kt_double m_DistanceVariancePenalty, m_MinimumDistancePenalty;
    kt_double m_AngleVariancePenalty, m_MinimumAnglePenalty;
    kt_double m_SearchCenterHeading;
    kt_int32u m_nX, m_nAngles;
    ScanMatcherGridSet* m_pScanMatcherGridSet;
  };
#endif
  
  kt_double ScanMatcher::CorrelateScan(ScanMatcherGridSet* pScanMatcherGridSet, LocalizedLaserScan* pScan, const Pose2& rSearchCenter, const Vector2d& rSearchSpaceOffset, const Vector2d& rSearchSpaceResolution,
                                       kt_double searchAngleOffset, kt_double searchAngleResolution,	kt_bool doPenalize, Pose2& rMean, Matrix3& rCovariance, kt_bool doingFineMatch)
  {
    assert(searchAngleResolution != 0.0);

    CorrelationGrid* pCorrelationGrid = pScanMatcherGridSet->m_pCorrelationGrid;
    Grid<kt_double>* pSearchSpaceProbs = pScanMatcherGridSet->m_pSearchSpaceProbs;
    GridIndexLookup<kt_int8u>* pGridLookup = pScanMatcherGridSet->m_pGridLookup;

    // setup lookup arrays
    pGridLookup->ComputeOffsets(pScan, rSearchCenter.GetHeading(), searchAngleOffset, searchAngleResolution);
    
    // only initialize probability grid if computing positional covariance (during coarse match)
    if (!doingFineMatch)
    {
      pSearchSpaceProbs->Clear();
      
      // position search grid - finds lower left corner of search grid
      Vector2d offset(rSearchCenter.GetPosition() - rSearchSpaceOffset);
      pSearchSpaceProbs->GetCoordinateConverter()->SetOffset(offset);
    }
    
    // calculate position arrays
    
    kt_int32u nX = static_cast<kt_int32u>(math::Round(rSearchSpaceOffset.GetX() * 2.0 / rSearchSpaceResolution.GetX()) + 1);
    std::vector<kt_double> xPoses(nX), newPositionsX(nX), squaresX(nX);
    kt_double startX = -rSearchSpaceOffset.GetX();
    for (kt_int32u xIndex = 0; xIndex < nX; xIndex++)
    {
      kt_double x = startX + xIndex * rSearchSpaceResolution.GetX();
      xPoses[xIndex] = x;
      newPositionsX[xIndex] = rSearchCenter.GetX() + x;
      squaresX[xIndex] = math::Square(x);
    }
    assert(math::DoubleEqual(xPoses.back(), -startX));
    
    kt_int32u nY = static_cast<kt_int32u>(math::Round(rSearchSpaceOffset.GetY() * 2.0 / rSearchSpaceResolution.GetY()) + 1);
    std::vector<kt_double> yPoses(nY), newPositionsY(nY), squaresY(nY);
    kt_double startY = -rSearchSpaceOffset.GetY();
    for (kt_int32u yIndex = 0; yIndex < nY; yIndex++)
    {
      kt_double y = startY + yIndex * rSearchSpaceResolution.GetY();
      yPoses[yIndex] = y;
      newPositionsY[yIndex] = rSearchCenter.GetY() + y;
      squaresY[yIndex] = math::Square(y);
    }
    assert(math::DoubleEqual(yPoses.back(), -startY));
    
    // calculate pose response array size
    kt_int32u nAngles = static_cast<kt_int32u>(math::Round(searchAngleOffset * 2.0 / searchAngleResolution) + 1);
    std::vector<kt_double> angles(nAngles);
    kt_double angle = 0.0;
    kt_double startAngle = rSearchCenter.GetHeading() - searchAngleOffset;
    for (kt_int32u angleIndex = 0; angleIndex < nAngles; angleIndex++)
    {
      angle = startAngle + angleIndex * searchAngleResolution;
      angles[angleIndex] = angle;
    }
    assert(math::DoubleEqual(angle, rSearchCenter.GetHeading() + searchAngleOffset));
    
    // allocate array
    kt_int32u poseResponseSize = nX * nY * nAngles;
    std::vector<std::pair<kt_double, Pose2> > poseResponses = std::vector<std::pair<kt_double, Pose2> >(poseResponseSize);
    
    Vector2i startGridPoint = pCorrelationGrid->WorldToGrid(Vector2d(rSearchCenter.GetX() + startX, rSearchCenter.GetY() + startY));
    
    // use tbb if enabled and in multi threaded mode!
    kt_bool gotTbb = false;
    if (m_pOpenMapper->IsMultiThreaded())
    {
#ifdef USE_TBB
      gotTbb = true;
      Parallel_CorrelateScan myTask(&newPositionsY, &squaresY, &newPositionsX, &squaresX, &angles,
        &poseResponses, this, doPenalize,
        m_pOpenMapper->m_pDistanceVariancePenalty->GetValue(),
        m_pOpenMapper->m_pMinimumDistancePenalty->GetValue(),
        m_pOpenMapper->m_pAngleVariancePenalty->GetValue(),
        m_pOpenMapper->m_pMinimumAnglePenalty->GetValue(),
        rSearchCenter.GetHeading(), pScanMatcherGridSet);
      int grainSizeY = 10;
      int grainSizeX = 10;
      int grainSizeAngle = 10;
      tbb::parallel_for(tbb::blocked_range3d<kt_int32s>(0, static_cast<kt_int32s>(nY), grainSizeY, 0, static_cast<kt_int32s>(nX), grainSizeX, 0, nAngles, grainSizeAngle), myTask);
#endif
    }

    // fallback to single threaded calculation
    if (gotTbb == false)
    {
      kt_int32u poseResponseCounter = 0;
      for (kt_int32u yIndex = 0; yIndex < nY; yIndex++)
      {
        kt_double newPositionY = newPositionsY[yIndex];
        kt_double squareY = squaresY[yIndex];

        for (kt_int32u xIndex = 0; xIndex < nX; xIndex++)
        {
          kt_double newPositionX = newPositionsX[xIndex];
          kt_double squareX = squaresX[xIndex];

          Vector2i gridPoint = pCorrelationGrid->WorldToGrid(Vector2d(newPositionX, newPositionY));
          kt_int32s gridIndex = pCorrelationGrid->GridIndex(gridPoint);
          assert(gridIndex >= 0);

          kt_double squaredDistance = squareX + squareY;
          for (kt_int32u angleIndex = 0; angleIndex < nAngles; angleIndex++)
          {
            kt_double angle = angles[angleIndex];

            kt_double response = GetResponse(pScanMatcherGridSet, angleIndex, gridIndex);
            if (doPenalize && (math::DoubleEqual(response, 0.0) == false))
            {
              // simple model (approximate Gaussian) to take odometry into account

              kt_double distancePenalty = 1.0 - (DISTANCE_PENALTY_GAIN * squaredDistance / m_pOpenMapper->m_pDistanceVariancePenalty->GetValue());
              distancePenalty = math::Maximum(distancePenalty, m_pOpenMapper->m_pMinimumDistancePenalty->GetValue());

              kt_double squaredAngleDistance = math::Square(angle - rSearchCenter.GetHeading());
              kt_double anglePenalty = 1.0 - (ANGLE_PENALTY_GAIN * squaredAngleDistance / m_pOpenMapper->m_pAngleVariancePenalty->GetValue());
              anglePenalty = math::Maximum(anglePenalty, m_pOpenMapper->m_pMinimumAnglePenalty->GetValue());

              response *= (distancePenalty * anglePenalty);
            }

            // store response and pose
            poseResponses[poseResponseCounter] = std::pair<kt_double, Pose2>(response, Pose2(newPositionX, newPositionY, math::NormalizeAngle(angle)));
            poseResponseCounter++;
          }        
        }
      }

      assert(poseResponseSize == poseResponseCounter);
    }
    
    // find value of best response (in [0; 1])
    kt_double bestResponse = -1;
    for (kt_int32u i = 0; i < poseResponseSize; i++)
    {
      bestResponse = math::Maximum(bestResponse, poseResponses[i].first);
      
      // will compute positional covariance, save best relative probability for each cell
      if (!doingFineMatch)
      {
        const Pose2& rPose = poseResponses[i].second;
        Vector2i grid = pSearchSpaceProbs->WorldToGrid(rPose.GetPosition());
        
        kt_double* ptr = (kt_double*)pSearchSpaceProbs->GetDataPointer(grid);
        if (ptr == NULL)
        {
          throw Exception("Mapper FATAL ERROR - Index out of range in probability search!");
        }
        
        *ptr = math::Maximum(poseResponses[i].first, *ptr);
      }
    }
    
    // average all poses with same highest response
    Vector2d averagePosition;
    kt_double thetaX = 0.0;
    kt_double thetaY = 0.0;
    kt_int32s averagePoseCount = 0;
    for (kt_int32u i = 0; i < poseResponseSize; i++)
    {
      if (math::DoubleEqual(poseResponses[i].first, bestResponse))
      {
        averagePosition += poseResponses[i].second.GetPosition();
        
        kt_double heading = poseResponses[i].second.GetHeading();
        thetaX += cos(heading);
        thetaY += sin(heading);
        
        averagePoseCount++;
      }
    }
    
    Pose2 averagePose;
    if (averagePoseCount > 0)
    {
      averagePosition /= averagePoseCount;
      
      thetaX /= averagePoseCount;
      thetaY /= averagePoseCount;
      
      averagePose = Pose2(averagePosition, atan2(thetaY, thetaX));
    }
    else
    {
      throw Exception("Mapper FATAL ERROR - Unable to find best position");
    }
    
#ifdef KARTO_DEBUG
    std::cout << "bestPose: " << averagePose << std::endl;
    std::cout << "bestResponse: " << bestResponse << std::endl;
#endif
    
    if (!doingFineMatch)
    {
      ComputePositionalCovariance(pSearchSpaceProbs, averagePose, bestResponse, rSearchCenter, rSearchSpaceOffset, rSearchSpaceResolution, searchAngleResolution, rCovariance);
    }
    else
    {
      ComputeAngularCovariance(pScanMatcherGridSet, averagePose, bestResponse, rSearchCenter, searchAngleOffset, searchAngleResolution, rCovariance);
    }
    
    rMean = averagePose;
    
#ifdef KARTO_DEBUG
    std::cout << "bestPose: " << averagePose << std::endl;
#endif
    
    if (bestResponse > 1.0)
    {
      bestResponse = 1.0;
    }
    
    assert(math::InRange(bestResponse, 0.0, 1.0));
    assert(math::InRange(rMean.GetHeading(), -KT_PI, KT_PI));
    
    return bestResponse;
  }
  
  void ScanMatcher::ComputePositionalCovariance(Grid<kt_double>* pSearchSpaceProbs, const Pose2& rBestPose, kt_double bestResponse,
                                                const Pose2& rSearchCenter, const Vector2d& rSearchSpaceOffset,
                                                const Vector2d& rSearchSpaceResolution, kt_double searchAngleResolution, Matrix3& rCovariance)
  {
    // reset covariance to identity matrix
    rCovariance.SetToIdentity();
    
    // if best response is vary small return max variance
    if (bestResponse < KT_TOLERANCE)
    {
      rCovariance(0, 0) = MAX_VARIANCE; // XX
      rCovariance(1, 1) = MAX_VARIANCE; // YY
      rCovariance(2, 2) = 4 * math::Square(searchAngleResolution); // TH*TH
      
      return;
    }
    
    kt_double accumulatedVarianceXX = 0;
    kt_double accumulatedVarianceXY = 0;
    kt_double accumulatedVarianceYY = 0;
    kt_double norm = 0;
    
    kt_double dx = rBestPose.GetX() - rSearchCenter.GetX();
    kt_double dy = rBestPose.GetY() - rSearchCenter.GetY();
    
    kt_double offsetX = rSearchSpaceOffset.GetX();
    kt_double offsetY = rSearchSpaceOffset.GetY();
    
    kt_int32u nX = static_cast<kt_int32u>(math::Round(offsetX * 2.0 / rSearchSpaceResolution.GetX()) + 1);
    kt_double startX = -offsetX;
    assert(math::DoubleEqual(startX + (nX - 1) * rSearchSpaceResolution.GetX(), -startX));
    
    kt_int32u nY = static_cast<kt_int32u>(math::Round(offsetY * 2.0 / rSearchSpaceResolution.GetY()) + 1);
    kt_double startY = -offsetY;
    assert(math::DoubleEqual(startY + (nY - 1) * rSearchSpaceResolution.GetY(), -startY));
    
    for (kt_int32u yIndex = 0; yIndex < nY; yIndex++)
    {
      kt_double y = startY + yIndex * rSearchSpaceResolution.GetY();
      
      for (kt_int32u xIndex = 0; xIndex < nX; xIndex++)
      {
        kt_double x = startX + xIndex * rSearchSpaceResolution.GetX();
        
        Vector2i gridPoint = pSearchSpaceProbs->WorldToGrid(Vector2d(rSearchCenter.GetX() + x, rSearchCenter.GetY() + y));
        kt_double response = *(pSearchSpaceProbs->GetDataPointer(gridPoint));
        
        // response is not a low response
        if (response >= (bestResponse - 0.1))
        {
          norm += response;
          accumulatedVarianceXX += (math::Square(x - dx) * response);
          accumulatedVarianceXY += ((x - dx) * (y - dy) * response);
          accumulatedVarianceYY += (math::Square(y - dy) * response);
        }
      }
    }
    
    if (norm > KT_TOLERANCE)
    {
      kt_double varianceXX = accumulatedVarianceXX / norm;
      kt_double varianceXY = accumulatedVarianceXY / norm;
      kt_double varianceYY = accumulatedVarianceYY / norm;
      kt_double varianceTHTH = 4 * math::Square(searchAngleResolution);
      
      // lower-bound variances so that they are not too small;
      // ensures that links are not too tight
      kt_double minVarianceXX = 0.1 * math::Square(rSearchSpaceResolution.GetX());
      kt_double minVarianceYY = 0.1 * math::Square(rSearchSpaceResolution.GetY());
      varianceXX = math::Maximum(varianceXX, minVarianceXX);
      varianceYY = math::Maximum(varianceYY, minVarianceYY);
      
      // increase variance for poorer responses
      kt_double multiplier = 1.0 / bestResponse;
      rCovariance(0, 0) = varianceXX * multiplier;
      rCovariance(0, 1) = varianceXY * multiplier;
      rCovariance(1, 0) = varianceXY * multiplier;
      rCovariance(1, 1) = varianceYY * multiplier;
      rCovariance(2, 2) = varianceTHTH; // this value will be set in ComputeAngularCovariance
    }
    
    // if values are 0, set to MAX_VARIANCE
    // values might be 0 if points are too sparse and thus don't hit other points
    if (math::DoubleEqual(rCovariance(0, 0), 0.0))
    {
      rCovariance(0, 0) = MAX_VARIANCE;
    }
    
    if (math::DoubleEqual(rCovariance(1, 1), 0.0))
    {
      rCovariance(1, 1) = MAX_VARIANCE;
    }
  }
  
  void ScanMatcher::ComputeAngularCovariance(ScanMatcherGridSet* pScanMatcherGridSet, const Pose2& rBestPose, kt_double bestResponse, const Pose2& rSearchCenter,
                                             kt_double searchAngleOffset, kt_double searchAngleResolution, Matrix3& rCovariance)
  {
    // NOTE: do not reset covariance matrix
    
    CorrelationGrid* pCorrelationGrid = pScanMatcherGridSet->m_pCorrelationGrid;
    
    // normalize angle difference
    kt_double bestAngle = math::NormalizeAngleDifference(rBestPose.GetHeading(), rSearchCenter.GetHeading());
    
    Vector2i gridPoint = pCorrelationGrid->WorldToGrid(rBestPose.GetPosition());
    kt_int32s gridIndex = pCorrelationGrid->GridIndex(gridPoint);
    
    kt_int32u nAngles = static_cast<kt_int32u>(math::Round(searchAngleOffset * 2 / searchAngleResolution) + 1);
    
    kt_double angle = 0.0;
    kt_double startAngle = rSearchCenter.GetHeading() - searchAngleOffset;
    
    kt_double norm = 0.0;
    kt_double accumulatedVarianceThTh = 0.0;
    for (kt_int32u angleIndex = 0; angleIndex < nAngles; angleIndex++)
    {
      angle = startAngle + angleIndex * searchAngleResolution;
      kt_double response = GetResponse(pScanMatcherGridSet, angleIndex, gridIndex);
      
      // response is not a low response
      if (response >= (bestResponse - 0.1))
      {
        norm += response;
        accumulatedVarianceThTh += (math::Square(angle - bestAngle) * response);
      }
    }
    assert(math::DoubleEqual(angle, rSearchCenter.GetHeading() + searchAngleOffset));
    
    if (norm > KT_TOLERANCE)
    {
      if (accumulatedVarianceThTh < KT_TOLERANCE)
      {
        accumulatedVarianceThTh = math::Square(searchAngleResolution);
      }
      
      accumulatedVarianceThTh /= norm;
    }
    else
    {
      accumulatedVarianceThTh = 1000 * math::Square(searchAngleResolution);
    }
    
    rCovariance(2, 2) = accumulatedVarianceThTh;
  }
  
  void ScanMatcher::AddScans(CorrelationGrid* pCorrelationGrid, const LocalizedLaserScanList& rScans, const Vector2d& rViewPoint)
  {
    pCorrelationGrid->Clear();
    
    // add all scans to grid
    karto_const_forEach(LocalizedLaserScanList, &rScans)
    {
      AddScan(pCorrelationGrid, *iter, rViewPoint);
    }
  }
  
  void ScanMatcher::AddScansNew(CorrelationGrid* pCorrelationGrid, const LocalizedLaserScanList& rScans, const Vector2d& rViewPoint)
  {
    pCorrelationGrid->Clear();

    kt_int32s index = 0;
    kt_size_t nScans = rScans.Size();
    Vector2dList* pValidPoints = new Vector2dList[nScans];

    // first find all valid points
//#pragma omp parallel for
//    for (kt_int32s i = 0; i < nScans; i++)
//    {
//      pValidPoints[i] = FindValidPoints(rScans[i], rViewPoint);
//    }

    karto_const_forEach(LocalizedLaserScanList, &rScans)
    {
      pValidPoints[index++] = FindValidPoints(*iter, rViewPoint);
    }

    // then add all valid points to correlation grid
    for (kt_size_t i = 0; i < nScans; i++)
    {
      AddScanNew(pCorrelationGrid, pValidPoints[i]);
    }

    delete[] pValidPoints;
  }

  void ScanMatcher::AddScan(CorrelationGrid* pCorrelationGrid, LocalizedLaserScan* pScan, const Vector2d& rViewPoint, kt_bool doSmear)
  {
    Vector2dList validPoints = FindValidPoints(pScan, rViewPoint);
    
    // put in all valid points
    karto_const_forEach(Vector2dList, &validPoints)
    {
      Vector2i gridPoint = pCorrelationGrid->WorldToGrid(*iter);
      if (!math::IsUpTo(gridPoint.GetX(), pCorrelationGrid->GetROI().GetWidth()) || !math::IsUpTo(gridPoint.GetY(), pCorrelationGrid->GetROI().GetHeight()))
      {
        // point not in grid
        continue;
      }
      
      int gridIndex = pCorrelationGrid->GridIndex(gridPoint);
      
      // set grid cell as occupied
      if (pCorrelationGrid->GetDataPointer()[gridIndex] == GridStates_Occupied)
      {
        // value already set
        continue;
      }
      
      pCorrelationGrid->GetDataPointer()[gridIndex] = GridStates_Occupied;
      
      // smear grid
      if (doSmear == true)
      {
        pCorrelationGrid->SmearPoint(gridPoint);        
      }
    }
  }
  
  void ScanMatcher::AddScanNew(CorrelationGrid* pCorrelationGrid, const Vector2dList& rValidPoints, kt_bool doSmear)
  {
    // put in all valid points
    karto_const_forEach(Vector2dList, &rValidPoints)
    {
      Vector2i gridPoint = pCorrelationGrid->WorldToGrid(*iter);
      if (!math::IsUpTo(gridPoint.GetX(), pCorrelationGrid->GetROI().GetWidth()) || !math::IsUpTo(gridPoint.GetY(), pCorrelationGrid->GetROI().GetHeight()))
      {
        // point not in grid
        continue;
      }

      int gridIndex = pCorrelationGrid->GridIndex(gridPoint);

      // set grid cell as occupied
      if (pCorrelationGrid->GetDataPointer()[gridIndex] == GridStates_Occupied)
      {
        // value already set
        continue;
      }

      pCorrelationGrid->GetDataPointer()[gridIndex] = GridStates_Occupied;

      // smear grid
      if (doSmear == true)
      {
        pCorrelationGrid->SmearPoint(gridPoint);
      }
    }
  }

  Vector2dList ScanMatcher::FindValidPoints(LocalizedLaserScan* pScan, const Vector2d& rViewPoint)
  {
    const Vector2dList& rPointReadings = pScan->GetPointReadings(true);
    
    // points must be at least 10 cm away when making comparisons of inside/outside of viewpoint
    const kt_double minSquareDistance = math::Square(0.1); // in m^2
    
    // this iterator lags from the main iterator adding points only when the points are on
    // the same side as the viewpoint
    Vector2dList::ConstIterator trailingPointIter = rPointReadings.GetConstIterator();
    Vector2dList validPoints;
    
    Vector2d firstPoint;
    kt_bool firstTime = true;
    karto_const_forEach(Vector2dList, &rPointReadings)
    {
      Vector2d currentPoint = *iter;
      
      if (firstTime)
      {
        firstPoint = currentPoint;
        firstTime = false;
      }
      
      Vector2d delta = firstPoint - currentPoint;
      if (delta.SquaredLength() > minSquareDistance)
      {
        // This compute the Determinant (viewPoint FirstPoint, viewPoint currentPoint)
        // Which computes the direction of rotation, if the rotation is counterclock
        // wise then we are looking at data we should keep. If it's negative rotation
        // we should not included in in the matching
        // have enough distance, check viewpoint
        double a = rViewPoint.GetY() - firstPoint.GetY();
        double b = firstPoint.GetX() - rViewPoint.GetX();
        double c = firstPoint.GetY() * rViewPoint.GetX() - firstPoint.GetX() * rViewPoint.GetY();
        double ss = currentPoint.GetX() * a + currentPoint.GetY() * b + c;
        
        // reset beginning point
        firstPoint = currentPoint;
        
        if (ss < 0.0)	// wrong side, skip and keep going
        {
          trailingPointIter = iter;
        }
        else
        {
          for (; trailingPointIter != iter; trailingPointIter++)
          {
            validPoints.Add(*trailingPointIter);
          }
        }
      }
    }
    
    return validPoints;
  }  
  
  kt_double ScanMatcher::GetResponse(ScanMatcherGridSet* pScanMatcherGridSet, kt_int32u angleIndex, kt_int32s gridPositionIndex)
  {
    CorrelationGrid* pCorrelationGrid = pScanMatcherGridSet->m_pCorrelationGrid;
    GridIndexLookup<kt_int8u>* pGridLookup = pScanMatcherGridSet->m_pGridLookup;
    
    kt_double response = 0.0;
    
    // add up value for each point
    kt_int8u* pByte = pCorrelationGrid->GetDataPointer() + gridPositionIndex;
    
    const LookupArray* pOffsets = pGridLookup->GetLookupArray(angleIndex);
    assert(pOffsets != NULL);
    
    // get number of points in offset list
    kt_int32u nPoints = pOffsets->GetSize();
    if (nPoints == 0)
    {
      return response;
    }
    
    // calculate response
    kt_int32s* pAngleIndexPointer = pOffsets->GetArrayPointer();
    for (kt_int32u i = 0; i < nPoints; i++)
    {
      // ignore points that fall off the grid
      kt_int32s pointGridIndex = gridPositionIndex + pAngleIndexPointer[i];
      if (!math::IsUpTo(pointGridIndex, pCorrelationGrid->GetDataSize()))
      {
        continue;
      }

      // uses index offsets to efficiently find location of point in the grid
      response += pByte[pAngleIndexPointer[i]];
    }
    
    // normalize response
    response /= (nPoints * GridStates_Occupied);
    assert(fabs(response) <= 1.0);
    
    return response;
  }
  
  CorrelationGrid* ScanMatcher::GetCorrelationGrid() const
  {
    if (m_pOpenMapper->IsMultiThreaded())
    {
      throw Exception("Correlation grid only available in single-threaded mode");
    }
    else
    {
      return m_pScanMatcherGridSet->m_pCorrelationGrid;
    }
  }
  
  Grid<kt_double>* ScanMatcher::GetSearchGrid() const
  {
    if (m_pOpenMapper->IsMultiThreaded())
    {
      throw Exception("Search grid only available in single-threaded mode");
    }
    else
    {
      return m_pScanMatcherGridSet->m_pSearchSpaceProbs;
    }
  }
  
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  template<typename T>
  class BreadthFirstTraversal : public GraphTraversal<T>
  {
  public:
    /**
     * Constructs a breadth-first traverser for the given graph
     */
    BreadthFirstTraversal(Graph<T>* pGraph)
      : GraphTraversal<T>(pGraph)
    {
    }

    /**
     * Destructor
     */
    virtual ~BreadthFirstTraversal()
    {
    }

  public:
    /**
     * Traverse the graph starting with the given vertex; applies the visitor to visited nodes
     * @param pStartVertex
     * @param pVisitor
     * @return visited vertices
     */
    virtual List<T> Traverse(Vertex<T>* pStartVertex, Visitor<T>* pVisitor)
    {
      std::queue<Vertex<T>*> toVisit;
      std::set<Vertex<T>*> seenVertices;
      std::vector<Vertex<T>*> validVertices;

      toVisit.push(pStartVertex);
      seenVertices.insert(pStartVertex);

      do
      {
        Vertex<T>* pNext = toVisit.front();
        toVisit.pop();

        if (pVisitor->Visit(pNext))  // Distance to pScan is less than m_MaxDistanceSquared
        {
          // vertex is valid, explore neighbors
          validVertices.push_back(pNext);

          List<Vertex<T>*> adjacentVertices = pNext->GetAdjacentVertices();
          karto_const_forEach(typename List<Vertex<T>*>, &adjacentVertices)
          {
            Vertex<T>* pAdjacent = *iter;

            // adjacent vertex has not yet been seen, add to queue for processing
            if (seenVertices.find(pAdjacent) == seenVertices.end())
            {
              toVisit.push(pAdjacent);
              seenVertices.insert(pAdjacent);
            }
          }
        }
      } while (toVisit.empty() == false);

      List<T> objects;
      forEach(typename std::vector<Vertex<T>*>, &validVertices)
      {
        objects.Add((*iter)->GetVertexObject());
      }

      return objects;
    }

  }; // class BreadthFirstTraversal

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  class NearScanVisitor : public Visitor<LocalizedObjectPtr>
  {
  public:
    NearScanVisitor(LocalizedLaserScan* pScan, kt_double maxDistance, kt_bool useScanBarycenter)
      : m_MaxDistanceSquared(math::Square(maxDistance))
      , m_UseScanBarycenter(useScanBarycenter)
    {
      m_CenterPose = pScan->GetReferencePose(m_UseScanBarycenter);
    }

    virtual kt_bool Visit(Vertex<LocalizedObjectPtr>* pVertex)
    {
      LocalizedObject* pObject = pVertex->GetVertexObject();

      LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
      
      // object is not a scan or wasn't scan matched, ignore
      if (pScan == NULL)
      {
        return false;
      }
      
      Pose2 pose = pScan->GetReferencePose(m_UseScanBarycenter);

      kt_double squaredDistance = pose.GetPosition().SquaredDistance(m_CenterPose.GetPosition());
      return (squaredDistance <= m_MaxDistanceSquared - KT_TOLERANCE);
    }

  protected:
    Pose2 m_CenterPose;
    kt_double m_MaxDistanceSquared;
    kt_bool m_UseScanBarycenter;

  }; // NearScanVisitor

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  MapperGraph::MapperGraph(OpenMapper* pOpenMapper, kt_double rangeThreshold)
    : m_pOpenMapper(pOpenMapper)
  {
    mCountLoop = 0;
    m_pLoopScanMatcher = ScanMatcher::Create(pOpenMapper, m_pOpenMapper->m_pLoopSearchSpaceDimension->GetValue(), m_pOpenMapper->m_pLoopSearchSpaceResolution->GetValue(), m_pOpenMapper->m_pLoopSearchSpaceSmearDeviation->GetValue(), rangeThreshold);
    assert(m_pLoopScanMatcher);
    
    m_pTraversal = new BreadthFirstTraversal<LocalizedObjectPtr>(this);
  }
  
  MapperGraph::~MapperGraph()
  {
    delete m_pLoopScanMatcher;
    m_pLoopScanMatcher = NULL;
    
    delete m_pTraversal;
    m_pTraversal = NULL;
  }
  
  void MapperGraph::AddVertex(LocalizedObject* pObject)
  {
    assert(pObject);

    if (pObject == NULL)
    {
      return;
    }
    
    Vertex<LocalizedObjectPtr>* pVertex = new Vertex<LocalizedObjectPtr>(pObject);
    Graph<LocalizedObjectPtr>::AddVertex(pVertex);
    if (m_pOpenMapper->m_pScanSolver != NULL)
    {
      m_pOpenMapper->m_pScanSolver->AddNode(pVertex);
    }
  }

  void MapperGraph::AddEdges(LocalizedObject* pObject)
  {
    // loose "spring"
    Matrix3 covariance;
    covariance(0, 0) = MAX_VARIANCE;
    covariance(1, 1) = MAX_VARIANCE;
    covariance(2, 2) = MAX_VARIANCE;
    
    LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
    if (pScan != NULL)
    {      
      AddEdges(pScan, covariance, false, 0.0);
    }
    else
    {
      MapperSensorManager* pSensorManager = m_pOpenMapper->m_pMapperSensorManager;      
      const Identifier& rSensorName = pObject->GetSensorIdentifier();
      
      LocalizedLaserScan* pLastScan = pSensorManager->GetLastScan(rSensorName);
      if (pLastScan != NULL)
      {
        ConstraintCreationContext context;
        context.provenance = ConstraintProvenance_CustomObjectLastScan;
        context.creationFunction = "MapperGraph::AddEdges(LocalizedObject*)";
        context.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
        LinkObjects(pLastScan, pObject, pObject->GetCorrectedPose(), covariance,
                    context);
      }
    }
  }

  void MapperGraph::AddEdges(LocalizedLaserScan* pScan, const Matrix3& rCovariance,
                             kt_bool hasMatchResponse, kt_double matchResponse)
  {
    MapperSensorManager* pSensorManager = m_pOpenMapper->m_pMapperSensorManager;
    
    const Identifier& rSensorName = pScan->GetSensorIdentifier();
    
    Pose2List means;
    List<Matrix3> covariances;
    
    LocalizedLaserScan* pLastScan = pSensorManager->GetLastScan(rSensorName);
    if (pLastScan == NULL)
    {
      // first scan (link to first scan of other robots)

      assert(pSensorManager->GetScans(rSensorName).Size() == 1);
      
      List<Identifier> sensorNames = pSensorManager->GetSensorNames();
      karto_const_forEach(List<Identifier>, &sensorNames)
      {
        const Identifier& rCandidateSensorName = *iter;
        
        // skip if candidate sensor is the same or other sensor has no scans
        if ((rCandidateSensorName == rSensorName) || (pSensorManager->GetScans(rCandidateSensorName).IsEmpty()))
        {
          continue;
        }
        
        Pose2 bestPose;
        Matrix3 covariance;
        kt_double response = m_pOpenMapper->m_pSequentialScanMatcher->MatchScan(pScan, pSensorManager->GetScans(rCandidateSensorName), bestPose, covariance);
        ConstraintCreationContext context;
        context.provenance = ConstraintProvenance_FirstScanCrossSensor;
        context.creationFunction = "MapperGraph::AddEdges(LocalizedLaserScan*)";
        context.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
        context.matcherType = "SEQUENTIAL_CROSS_SENSOR";
        context.hasMatchResponse = true;
        context.matchResponse = response;
        context.hasMatchThreshold = true;
        context.matchThreshold = m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue();
        LinkObjects(pSensorManager->GetScans(rCandidateSensorName)[0], pScan,
                    bestPose, covariance, context);
        
        // only add to means and covariances if response was high "enough"
        if (response > m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue())
        {
          means.Add(bestPose);
          covariances.Add(covariance);
        }
      }
    }
    else
    {
      // link to previous scan
      ConstraintCreationContext previousContext;
      previousContext.provenance = ConstraintProvenance_PreviousScan;
      previousContext.creationFunction = "MapperGraph::AddEdges(LocalizedLaserScan*)";
      previousContext.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
      previousContext.matcherType = "SEQUENTIAL_RUNNING_BUFFER";
      previousContext.hasMatchResponse = hasMatchResponse;
      previousContext.matchResponse = matchResponse;
      LinkObjects(pLastScan, pScan, pScan->GetSensorPose(), rCovariance,
                  previousContext);

      // link to running scans
      Pose2 scanPose = pScan->GetSensorPose();
      means.Add(scanPose);
      covariances.Add(rCovariance);
      ConstraintCreationContext runningContext;
      runningContext.provenance = ConstraintProvenance_RunningScanChain;
      runningContext.creationFunction = "MapperGraph::LinkChainToScan";
      runningContext.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
      runningContext.matcherType = "SEQUENTIAL_RUNNING_BUFFER";
      runningContext.hasMatchResponse = hasMatchResponse;
      runningContext.matchResponse = matchResponse;
      LinkChainToScan(pSensorManager->GetRunningScans(rSensorName), pScan,
                      scanPose, rCovariance, runningContext);
    }
    
    // link to other near chains (chains that include new scan are invalid)
    LinkNearChains(pScan, means, covariances);
    
    if (!means.IsEmpty())
    {
      pScan->SetSensorPose(ComputeWeightedMean(means, covariances));
    }
  }
  
  kt_bool MapperGraph::TryCloseLoop(LocalizedLaserScan* pScan, const Identifier& rSensorName)
  {
    kt_bool loopClosed = false;  // Identifier to whether perform PG optimization
    
    kt_int32u scanIndex = 0;

    // ---- Phase 2C observation-only: reset per loop-search diagnostic accumulators ----
    m_pOpenMapper->ResetLoopDiagnostics();
    
    LocalizedLaserScanList candidateChain = FindPossibleLoopClosure(pScan, rSensorName, scanIndex);  // Only return one valid loop chain
    if(candidateChain.IsEmpty()){
      // ROS_WARN("No loop closure find.");
    }
    
    kt_int32u chainAttempt = 0;
    while (!candidateChain.IsEmpty())
    {
#ifdef KARTO_DEBUG2
      std::cout << "Candidate chain for " << pScan->GetStateId() << ": [ ";
      karto_const_forEach(LocalizedLaserScanList, &candidateChain)
      {
        std::cout << (*iter)->GetStateId() << " ";
      }
      std::cout << "]" << std::endl;
#endif
        
      Pose2 bestPose;
      Matrix3 covariance;
      kt_double coarseResponse = m_pLoopScanMatcher->MatchScan(pScan, candidateChain, bestPose, covariance, false, false);
      
      StringBuilder message;
      message << "COARSE RESPONSE: " << coarseResponse << " (> " << m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue() << ")\n";
      message << "            var: " << covariance(0, 0) << ",  " << covariance(1, 1) << " (< " << m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue() << ")";
       
      MapperEventArguments eventArguments(message.ToString());
      m_pOpenMapper->Message.Notify(this, eventArguments);

      // ---- Phase 2C observation-only: classify the coarse outcome from the
      //      already-computed response and covariance. This never changes the
      //      original decision below. ----
      kt_bool coarsePass = false;
      std::string coarseReason = "NA";
      if (((coarseResponse > m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue()) &&
           (covariance(0, 0) < m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()) &&
           (covariance(1, 1) < m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()))
          ||
          ((coarseResponse > 0.9 * m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue()) &&
           (covariance(0, 0) < 0.01 * m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()) &&
           (covariance(1, 1) < 0.01 * m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue())))
      {
        coarsePass = true;
      }
      else
      {
        if (coarseResponse > m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue())
        {
          coarseReason = "COARSE_HIGH_VARIANCE";
        }
        else if (coarseResponse > 0.9 * m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue())
        {
          coarseReason = "COARSE_ALT_REJECT";
        }
        else
        {
          coarseReason = "COARSE_LOW_RESPONSE";
        }
      }
      
      if (((coarseResponse > m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue()) &&
           (covariance(0, 0) < m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()) &&
           (covariance(1, 1) < m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()))
          ||
          // be more lenient if the variance is really small
          ((coarseResponse > 0.9 * m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue()) &&
           (covariance(0, 0) < 0.01 * m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue()) &&
           (covariance(1, 1) < 0.01 * m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue())))
      {
        // save for reversion
        Pose2 oldPose = pScan->GetSensorPose();
        
        pScan->SetSensorPose(bestPose);
        kt_double fineResponse = m_pOpenMapper->m_pSequentialScanMatcher->MatchScan(pScan, candidateChain, bestPose, covariance, false);
        
        message.Clear();
        message << "FINE RESPONSE: " << fineResponse << " (>" << m_pOpenMapper->m_pLoopMatchMinimumResponseFine->GetValue() << ")";
        MapperEventArguments eventArguments(message.ToString());
        m_pOpenMapper->Message.Notify(this, eventArguments);
        
        if (fineResponse < m_pOpenMapper->m_pLoopMatchMinimumResponseFine->GetValue())
        {
          // failed verification test, revert
          pScan->SetSensorPose(oldPose);
          
          MapperEventArguments eventArguments("REJECTED!");
          m_pOpenMapper->Message.Notify(this, eventArguments);
          ROS_DEBUG("Fine LC failed. Actual: %f, Required: %f", fineResponse, m_pOpenMapper->m_pLoopMatchMinimumResponseFine->GetValue());

          // ---- Phase 2C observation-only: emit fine-reject record ----
          {
            std::ostringstream oss;
            oss << "{\"event\":\"loop_search_chain\","
                << m_pOpenMapper->BuildLoopDiagBaseFragment(pScan) << ","
                << "\"chain_attempt_index\":" << chainAttempt << ","
                << "\"chain_id\":" << chainAttempt << ","
                << LoopDiagChainFragment(candidateChain, pScan->GetStateId()) << ","
                << "\"coarse_attempted\":true,"
                << "\"coarse_response\":" << LoopDiagDouble(coarseResponse) << ","
                << "\"coarse_variance_x\":" << LoopDiagDouble(covariance(0, 0)) << ","
                << "\"coarse_variance_y\":" << LoopDiagDouble(covariance(1, 1)) << ","
                << "\"coarse_pass\":" << LoopDiagBool(coarsePass) << ","
                << "\"coarse_reject_reason\":null,"
                << "\"fine_attempted\":true,"
                << "\"fine_response\":" << LoopDiagDouble(fineResponse) << ","
                << "\"fine_pass\":false,"
                << "\"accepted\":false,"
                << "\"reject_stage\":\"FINE\","
                << "\"reject_reason\":\"FINE_LOW_RESPONSE\"}";
            m_pOpenMapper->AppendLoopDiagnosticsLine(oss.str());
          }
        }
        else
        {
          MapperEventArguments eventArguments1("Closing loop...");
          m_pOpenMapper->PreLoopClosed.Notify(this, eventArguments1);
          
          pScan->SetSensorPose(bestPose);

          // Observation-only identity snapshot. LinkChainToScan selects this same
          // closest scan from the same corrected current pose below. Capture the
          // exact endpoint and LinkInfo payload before graph optimization.
          LocalizedLaserScan* pObservedHistoricalScan = GetClosestScanToPose(
            candidateChain,
            pScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue()));
          LinkInfo observedLink(
            pObservedHistoricalScan->GetSensorPose(), bestPose, covariance);
          const Pose2 observedMeasurement = observedLink.GetPoseDifference();
          const Matrix3 observedCovariance = observedLink.GetCovariance();

          ConstraintCreationContext loopContext;
          loopContext.provenance = ConstraintProvenance_TryCloseLoop;
          loopContext.creationFunction = "MapperGraph::LinkChainToScan";
          loopContext.creationStage = "TRY_CLOSE_LOOP";
          loopContext.matcherType = "LOOP_COARSE_AND_SEQUENTIAL_FINE";
          loopContext.hasMatchResponse = true;
          loopContext.matchResponse = fineResponse;
          loopContext.hasMatchThreshold = true;
          loopContext.matchThreshold = m_pOpenMapper->m_pLoopMatchMinimumResponseFine->GetValue();
          loopContext.hasCoarseResponse = true;
          loopContext.coarseResponse = coarseResponse;
          loopContext.hasCoarseThreshold = true;
          loopContext.coarseThreshold = m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue();
          LinkChainToScan(candidateChain, pScan, bestPose, covariance, loopContext);
          CorrectPoses();

          MapperEventArguments eventArguments2("Loop closed!");
          m_pOpenMapper->PostLoopClosed.Notify(this, eventArguments2);
          
          m_pOpenMapper->ScansUpdated.Notify(this, karto::EventArguments::Empty());   

          mCountLoop++;
          ROS_WARN("Add one Loop closure. %d loops have been added.", mCountLoop);   

          // Phase 4A observation-only: expose the accepted closure with its Karto
          // state ids to the ROS layer (no behavior change).
          if (candidateChain.Size() > 0)
          {
            kt_int64s chainStart = candidateChain.Front()->GetStateId();
            kt_int64s chainEnd = candidateChain.Back()->GetStateId();
            std::ostringstream lcMsg;
            lcMsg << "LoopClosureObserved current_scan=" << pScan->GetStateId()
                  << " chain_start=" << chainStart << " chain_end=" << chainEnd
                  << " historical_scan=" << pObservedHistoricalScan->GetStateId()
                  << " measurement_dx=" << observedMeasurement.GetX()
                  << " measurement_dy=" << observedMeasurement.GetY()
                  << " measurement_dyaw=" << observedMeasurement.GetHeading()
                  << " covariance_xx=" << observedCovariance(0, 0)
                  << " covariance_xy=" << observedCovariance(0, 1)
                  << " covariance_xt=" << observedCovariance(0, 2)
                  << " covariance_yy=" << observedCovariance(1, 1)
                  << " covariance_yt=" << observedCovariance(1, 2)
                  << " covariance_tt=" << observedCovariance(2, 2);
            MapperEventArguments eventArgs3(lcMsg.str().c_str());
            m_pOpenMapper->LoopClosureObserved.Notify(this, eventArgs3);
          }

          loopClosed = true;

          // ---- Phase 2C observation-only: emit accepted record ----
          {
            std::ostringstream oss;
            oss << "{\"event\":\"loop_search_chain\","
                << m_pOpenMapper->BuildLoopDiagBaseFragment(pScan) << ","
                << "\"chain_attempt_index\":" << chainAttempt << ","
                << "\"chain_id\":" << chainAttempt << ","
                << LoopDiagChainFragment(candidateChain, pScan->GetStateId()) << ","
                << "\"coarse_attempted\":true,"
                << "\"coarse_response\":" << LoopDiagDouble(coarseResponse) << ","
                << "\"coarse_variance_x\":" << LoopDiagDouble(covariance(0, 0)) << ","
                << "\"coarse_variance_y\":" << LoopDiagDouble(covariance(1, 1)) << ","
                << "\"coarse_pass\":true,"
                << "\"coarse_reject_reason\":null,"
                << "\"fine_attempted\":true,"
                << "\"fine_response\":" << LoopDiagDouble(fineResponse) << ","
                << "\"fine_pass\":true,"
                << "\"accepted\":true,"
                << "\"reject_stage\":\"ACCEPTED\","
                << "\"reject_reason\":null}";
            m_pOpenMapper->AppendLoopDiagnosticsLine(oss.str());
          }
        }
      }else{
        ROS_DEBUG("Coarse LC failed. Actual: %f, Required: %f", coarseResponse, m_pOpenMapper->m_pLoopMatchMinimumResponseCoarse->GetValue());
        ROS_DEBUG("Value cov(0, 0): %f, cov(1, 1): %f. Required Max cov: %f", covariance(0, 0), covariance(1, 1), m_pOpenMapper->m_pLoopMatchMaximumVarianceCoarse->GetValue());

        // ---- Phase 2C observation-only: emit coarse-reject record ----
        {
          std::ostringstream oss;
          oss << "{\"event\":\"loop_search_chain\","
              << m_pOpenMapper->BuildLoopDiagBaseFragment(pScan) << ","
              << "\"chain_attempt_index\":" << chainAttempt << ","
              << "\"chain_id\":" << chainAttempt << ","
              << LoopDiagChainFragment(candidateChain, pScan->GetStateId()) << ","
              << "\"coarse_attempted\":true,"
              << "\"coarse_response\":" << LoopDiagDouble(coarseResponse) << ","
              << "\"coarse_variance_x\":" << LoopDiagDouble(covariance(0, 0)) << ","
              << "\"coarse_variance_y\":" << LoopDiagDouble(covariance(1, 1)) << ","
              << "\"coarse_pass\":false,"
              << "\"coarse_reject_reason\":\"" << coarseReason << "\","
              << "\"fine_attempted\":false,"
              << "\"fine_response\":null,"
              << "\"fine_pass\":null,"
              << "\"accepted\":false,"
              << "\"reject_stage\":\"COARSE\","
              << "\"reject_reason\":\"" << coarseReason << "\"}";
          m_pOpenMapper->AppendLoopDiagnosticsLine(oss.str());
        }
      }
      chainAttempt++;
      candidateChain = FindPossibleLoopClosure(pScan, rSensorName, scanIndex); // Seach for new loop closure chain from new scanIndex
    }
    // ---- Phase 2C observation-only: if no candidate chain was ever attempted,
    //      emit one no-chain record summarizing the candidate generation stage. ----
    if (m_pOpenMapper->m_DiagChainCount == 0)
    {
      std::ostringstream oss;
      std::string noChainReason = LoopDiagNoChainReason(
        m_pOpenMapper->m_DiagScansInDistance, m_pOpenMapper->m_DiagScansNearLinked);
      oss << "{\"event\":\"loop_search_no_chain\","
          << m_pOpenMapper->BuildLoopDiagBaseFragment(pScan) << ","
          << "\"chain_attempt_index\":null,"
          << "\"chain_id\":null,"
          << "\"chain_size\":0,\"scan_ids\":[],"
          << "\"min_scan_index_gap\":null,\"max_scan_index_gap\":null,"
          << "\"coarse_attempted\":false,"
          << "\"coarse_response\":null,"
          << "\"coarse_variance_x\":null,\"coarse_variance_y\":null,"
          << "\"coarse_pass\":null,\"coarse_reject_reason\":null,"
          << "\"fine_attempted\":false,"
          << "\"fine_response\":null,\"fine_pass\":null,"
          << "\"accepted\":false,"
          << "\"reject_stage\":\"CANDIDATE\","
          << "\"reject_reason\":\"" << noChainReason << "\"}";
      m_pOpenMapper->AppendLoopDiagnosticsLine(oss.str());
    }
    if(!loopClosed){
      ROS_DEBUG("Reject Loop closure.");
    }

    m_pOpenMapper->RecordTryCloseLoopContext(
      pScan, NULL, "POST_TRY_CLOSE_LOOP");
    
    return loopClosed;
  }
  
  LocalizedLaserScan* MapperGraph::GetClosestScanToPose(const LocalizedLaserScanList& rScans, const Pose2& rPose) const
  {
    LocalizedLaserScan* pClosestScan = NULL;
    kt_double bestSquaredDistance = DBL_MAX;
    
    karto_const_forEach(LocalizedLaserScanList, &rScans)
    {
      Pose2 scanPose = (*iter)->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());
      
      kt_double squaredDistance = rPose.GetPosition().SquaredDistance(scanPose.GetPosition());
      if (squaredDistance < bestSquaredDistance)
      {
        bestSquaredDistance = squaredDistance;
        pClosestScan = *iter;
      }
    }
    
    return pClosestScan;
  }
    
  Edge<LocalizedObjectPtr>* MapperGraph::AddEdge(LocalizedObject* pSourceObject, LocalizedObject* pTargetObject, kt_bool& rIsNewEdge)
  {
    // check that vertex exists
    assert(pSourceObject->GetUniqueId() < (kt_int32s)m_Vertices.Size());
    assert(pTargetObject->GetUniqueId() < (kt_int32s)m_Vertices.Size());
    
    Vertex<LocalizedObjectPtr>* v1 = m_Vertices[pSourceObject->GetUniqueId()];
    Vertex<LocalizedObjectPtr>* v2 = m_Vertices[pTargetObject->GetUniqueId()];
    
    // see if edge already exists
    karto_const_forEach(List<Edge<LocalizedObjectPtr>*>, &(v1->GetEdges()))
    {
      Edge<LocalizedObjectPtr>* pEdge = *iter;
      
      if (pEdge->GetTarget() == v2)
      {
        rIsNewEdge = false;
        return pEdge;
      }
    }
    
    Edge<LocalizedObjectPtr>* pEdge = new Edge<LocalizedObjectPtr>(v1, v2);
    Graph<LocalizedObjectPtr>::AddEdge(pEdge);
    rIsNewEdge = true;
    return pEdge;
  }
  
  void MapperGraph::LinkObjects(LocalizedObject* pFromObject, LocalizedObject* pToObject,
                                const Pose2& rMean, const Matrix3& rCovariance,
                                const ConstraintCreationContext& rContext)
  {
    kt_bool isNewEdge = true;
    Edge<LocalizedObjectPtr>* pEdge = AddEdge(pFromObject, pToObject, isNewEdge);
    // pFromObject.getUniqueID()
    pEdge->AddCovariance(rCovariance);
    // std::tuple<int, int> curr_edge_cov(1, 2);
    // covariance_lists.push_back(curr_edge_cov);
    
    // only attach link information if the edge is new
    if (isNewEdge == true)
    {
      LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pFromObject);
      if (pScan != NULL)
      {
        pEdge->SetLabel(new LinkInfo(pScan->GetSensorPose(), rMean, rCovariance));
      }
      else
      {
        pEdge->SetLabel(new LinkInfo(pFromObject->GetCorrectedPose(), rMean, rCovariance));
      }
      kt_bool solverAddConstraintCalled = false;
      if (m_pOpenMapper->m_pScanSolver != NULL)
      {
        m_pOpenMapper->m_pScanSolver->AddConstraint(pEdge);
        solverAddConstraintCalled = true;
      }
      m_pOpenMapper->RecordNewConstraint(
        pEdge, pFromObject, pToObject, rContext, solverAddConstraintCalled);
    }
  }
  
#ifdef USE_TBB
  class Parallel_LinkNearChains
  {
  public:
    Parallel_LinkNearChains(OpenMapper* pMapper, LocalizedLaserScan* pScan, const List<LocalizedLaserScanList>* pChains,
                            kt_bool* pWasChainLinked, Pose2List* pMeans, List<Matrix3>* pCovariances,
                            List<kt_double>* pResponses,
                            kt_int32u minChainSize, kt_double minResponse)
      : m_pOpenMapper(pMapper)
      , m_pScan(pScan)
      , m_pChains(pChains)
      , m_pWasChainLinked(pWasChainLinked)
      , m_pMeans(pMeans)
      , m_pCovariances(pCovariances)
      , m_pResponses(pResponses)
      , m_MinChainSize(minChainSize)
      , m_MinResponse(minResponse)
    {      
    }
    
    void operator()(const tbb::blocked_range<kt_int32s>& rRange) const
    {
      for (kt_int32s i = rRange.begin(); i != rRange.end(); i++)
      {
        m_pWasChainLinked[i] = false;

        const LocalizedLaserScanList& rChain = m_pChains->Get(i);
        
        if (rChain.Size() < m_MinChainSize)
        {
          continue;
        }

        Pose2 mean;
        Matrix3 covariance;
        
        // match scan against "near" chain
        kt_double response = m_pOpenMapper->GetSequentialScanMatcher()->MatchScan(m_pScan, rChain, mean, covariance, false);
        if (response > m_MinResponse - KT_TOLERANCE)
        {
          m_pWasChainLinked[i] = true;
          m_pMeans->Set(i, mean);
          m_pCovariances->Set(i, covariance);
          m_pResponses->Set(i, response);
        }
      }
    }

  private:
    OpenMapper* m_pOpenMapper;
    LocalizedLaserScan* m_pScan;
    const List<LocalizedLaserScanList>* m_pChains;
    kt_bool* m_pWasChainLinked;
    Pose2List* m_pMeans;
    List<Matrix3>* m_pCovariances;
    List<kt_double>* m_pResponses;
    kt_int32u m_MinChainSize;
    kt_double m_MinResponse;
  };
#endif
  
  void MapperGraph::LinkNearChains(LocalizedLaserScan* pScan, Pose2List& rMeans, List<Matrix3>& rCovariances)
  {
    const List<LocalizedLaserScanList> nearChains = FindNearChains(pScan);

    kt_bool gotTbb = false;
    if (m_pOpenMapper->IsMultiThreaded())
    {
#ifdef USE_TBB
      gotTbb = true;
      kt_bool* pWasChainLinked = new kt_bool[nearChains.Size()];

      Pose2List means;
      means.Resize(nearChains.Size());

      List<Matrix3> covariances;
      covariances.Resize(nearChains.Size());

      List<kt_double> responses;
      responses.Resize(nearChains.Size());

      int grainSize = 100;
      Parallel_LinkNearChains myTask(m_pOpenMapper, pScan, &nearChains, pWasChainLinked,
        &means, &covariances, &responses,
        m_pOpenMapper->m_pLoopMatchMinimumChainSize->GetValue(),
        m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue());
      tbb::parallel_for(tbb::blocked_range<kt_int32s>(0, static_cast<kt_int32s>(nearChains.Size()), grainSize), myTask);

      for (kt_int32u i = 0; i < nearChains.Size(); i++)
      {
        if (pWasChainLinked[i] == true)
        {
          rMeans.Add(means[i]);
          rCovariances.Add(covariances[i]);
          ConstraintCreationContext context;
          context.provenance = ConstraintProvenance_NearChain;
          context.creationFunction = "MapperGraph::LinkChainToScan";
          context.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
          context.matcherType = "SEQUENTIAL_NEAR_CHAIN";
          context.hasMatchResponse = true;
          context.matchResponse = responses[i];
          context.hasMatchThreshold = true;
          context.matchThreshold = m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue();
          LinkChainToScan(nearChains[i], pScan, means[i], covariances[i], context);
        }
      }

      delete [] pWasChainLinked;
#endif
    }

    if (gotTbb == false)
    {
      karto_const_forEach(List<LocalizedLaserScanList>, &nearChains)
      {
#ifdef KARTO_DEBUG2
        std::cout << "Near chain for " << pScan->GetStateId() << ": [ ";
        karto_const_forEachAs(LocalizedLaserScanList, iter, iter2)
        {
          std::cout << (*iter2)->GetStateId() << " ";
        }
        std::cout << "]: ";
#endif

        if (iter->Size() < m_pOpenMapper->m_pLoopMatchMinimumChainSize->GetValue())
        {
#ifdef KARTO_DEBUG2
          std::cout << iter->Size() << "(< " << m_pOpenMapper->m_pLoopMatchMinimumChainSize->GetValue() << ") REJECTED" << std::endl;
#endif
          continue;
        }

        Pose2 mean;
        Matrix3 covariance;
        // match scan against "near" chain
        kt_double response = m_pOpenMapper->m_pSequentialScanMatcher->MatchScan(pScan, *iter, mean, covariance, false);
        if (response > m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue() - KT_TOLERANCE)
        {
#ifdef KARTO_DEBUG2
          std::cout << " ACCEPTED" << std::endl;
#endif
          rMeans.Add(mean);
          rCovariances.Add(covariance);
          ConstraintCreationContext context;
          context.provenance = ConstraintProvenance_NearChain;
          context.creationFunction = "MapperGraph::LinkChainToScan";
          context.creationStage = "ADD_EDGES_BEFORE_TRY_CLOSE_LOOP";
          context.matcherType = "SEQUENTIAL_NEAR_CHAIN";
          context.hasMatchResponse = true;
          context.matchResponse = response;
          context.hasMatchThreshold = true;
          context.matchThreshold = m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue();
          LinkChainToScan(*iter, pScan, mean, covariance, context);
        }
        else
        {
#ifdef KARTO_DEBUG2
          std::cout << response << "(< " << m_pOpenMapper->m_pLinkMatchMinimumResponseFine->GetValue() << ") REJECTED" << std::endl;
#endif        
        }
      }
    }
  }
  
  void MapperGraph::LinkChainToScan(const LocalizedLaserScanList& rChain,
                                    LocalizedLaserScan* pScan,
                                    const Pose2& rMean,
                                    const Matrix3& rCovariance,
                                    const ConstraintCreationContext& rContext)
  {
    Pose2 pose = pScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());

    LocalizedLaserScan* pClosestScan = GetClosestScanToPose(rChain, pose);
    assert(pClosestScan != NULL);

    Pose2 closestScanPose = pClosestScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());

    kt_double squaredDistance = pose.GetPosition().SquaredDistance(closestScanPose.GetPosition());
    if (squaredDistance < math::Square(m_pOpenMapper->m_pLinkScanMaximumDistance->GetValue()) + KT_TOLERANCE)
    {
      LinkObjects(pClosestScan, pScan, rMean, rCovariance, rContext); // From closest scan in the chain to pScan
#ifdef KARTO_DEBUG2
      std::cout << "Linking scan " << pScan->GetStateId() << " to chain scan " << pClosestScan->GetStateId() << std::endl;
#endif
    }
  }
  
  List<LocalizedLaserScanList> MapperGraph::FindNearChains(LocalizedLaserScan* pScan)
  {
    List<LocalizedLaserScanList> nearChains;
    
    Pose2 scanPose = pScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());
    
    // to keep track of which scans have been added to a chain
    LocalizedLaserScanList processed;
    
    const LocalizedLaserScanList nearLinkedScans = FindNearLinkedScans(pScan, m_pOpenMapper->m_pLinkScanMaximumDistance->GetValue());
    karto_const_forEach(LocalizedLaserScanList, &nearLinkedScans)
    {
      LocalizedLaserScan* pNearScan = *iter;
      
      if (pNearScan == pScan)
      {
        continue;
      }
      
      // scan has already been processed, skip
      if (processed.Contains(pNearScan) == true)
      {
        continue;
      }
      
#ifdef KARTO_DEBUG2
      std::cout << "BUILDING CHAIN: Scan " << pScan->GetStateId() << " is near " << pNearScan->GetStateId() << " (< " << m_pOpenMapper->m_pLinkScanMaximumDistance->GetValue() << ")" << std::endl;
#endif
      
      processed.Add(pNearScan);
      
      // build up chain
      kt_bool isValidChain = true;
      LocalizedLaserScanList chain;

      LocalizedLaserScanList scans = m_pOpenMapper->m_pMapperSensorManager->GetScans(pNearScan->GetSensorIdentifier());
      
      kt_int32s nearScanIndex = m_pOpenMapper->m_pMapperSensorManager->GetScanIndex(pNearScan);
      assert(nearScanIndex >= 0);
      
      // add scans before current scan being processed
      for (kt_int32s candidateScanIndex = nearScanIndex - 1; candidateScanIndex >= 0; candidateScanIndex--)
      {
        LocalizedLaserScan* pCandidateScan = scans[candidateScanIndex];
        
        // chain is invalid--contains scan being added
        if (pCandidateScan == pScan)
        {
#ifdef KARTO_DEBUG2
          std::cout << "INVALID CHAIN: Scan " << pScan->GetStateId() << " is not allowed in chain." << std::endl;
#endif
          isValidChain = false;
        }
        
        Pose2 candidatePose = pCandidateScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());
        kt_double squaredDistance = scanPose.GetPosition().SquaredDistance(candidatePose.GetPosition());
        
        if (squaredDistance < math::Square(m_pOpenMapper->m_pLinkScanMaximumDistance->GetValue()) + KT_TOLERANCE)
        {
          chain.Add(pCandidateScan);
          processed.Add(pCandidateScan);
          
#ifdef KARTO_DEBUG2
          std::cout << "Building chain for " << pScan->GetStateId() << ": [ ";
          karto_const_forEachAs(LocalizedLaserScanList, &chain, iter2)
          {
            std::cout << (*iter2)->GetStateId() << " ";
          }
          std::cout << "]" << std::endl;
#endif          
        }
        else
        {
          break;
        }
      }
      
      chain.Add(pNearScan);
      
      // add scans after current scan being processed
      kt_size_t end = scans.Size();
      for (kt_size_t candidateScanIndex = nearScanIndex + 1; candidateScanIndex < end; candidateScanIndex++)
      {
        LocalizedLaserScan* pCandidateScan = scans[candidateScanIndex];
        
        if (pCandidateScan == pScan)
        {
#ifdef KARTO_DEBUG2
          std::cout << "INVALID CHAIN: Scan " << pScan->GetStateId() << " is not allowed in chain." << std::endl;
#endif          
          isValidChain = false;
        }
        
        Pose2 candidatePose = pCandidateScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());;
        kt_double squaredDistance = scanPose.GetPosition().SquaredDistance(candidatePose.GetPosition());
        
        if (squaredDistance < math::Square(m_pOpenMapper->m_pLinkScanMaximumDistance->GetValue()) + KT_TOLERANCE)
        {
          chain.Add(pCandidateScan);
          processed.Add(pCandidateScan);
          
#ifdef KARTO_DEBUG2
          std::cout << "Building chain for " << pScan->GetStateId() << ": [ ";
          karto_const_forEachAs(LocalizedLaserScanList, &chain, iter2)
          {
            std::cout << (*iter2)->GetStateId() << " ";
          }
          std::cout << "]" << std::endl;
#endif                    
        }
        else
        {
          break;
        }
      }
      
      if (isValidChain)
      {
        // add chain to collection
        nearChains.Add(chain);
      }
    }
    
    return nearChains;
  }
  
  LocalizedLaserScanList MapperGraph::FindNearLinkedScans(LocalizedLaserScan* pScan, kt_double maxDistance)
  {
    NearScanVisitor* pVisitor = new NearScanVisitor(pScan, maxDistance, m_pOpenMapper->m_pUseScanBarycenter->GetValue()); // Here distance is maxDistance
    LocalizedObjectList nearLinkedObjects = m_pTraversal->Traverse(GetVertex(pScan), pVisitor);  // Here use another distance for fine neighbor finding
    delete pVisitor;
    
    LocalizedLaserScanList nearLinkedScans;
    karto_const_forEach(LocalizedObjectList, &nearLinkedObjects)
    {
      LocalizedObject* pObject = *iter;
      LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
      if (pScan != NULL)
      {
        nearLinkedScans.Add(pScan);
      }
    }
    
    return nearLinkedScans;
  }
  
  LocalizedLaserScanList MapperGraph::FindOverlappingScans(karto::LocalizedLaserScan *pScan)
  {
    LocalizedLaserScanList nearScans;

    const BoundingBox2& rBoundingBox = pScan->GetBoundingBox();
    
    const VertexList& vertices = GetVertices();
    karto_const_forEach(VertexList, &vertices)
    {
      LocalizedObject* pObject = (*iter)->GetVertexObject();
      LocalizedLaserScan* pCandidateScan = dynamic_cast<LocalizedLaserScan*>(pObject);
      if (pCandidateScan == NULL)
      {
        continue;
      }
      
      if (rBoundingBox.Intersects(pCandidateScan->GetBoundingBox()) == true)
      {
        nearScans.Add(pCandidateScan);
      }
    }
    
    return nearScans;
  }

  
  Pose2 MapperGraph::ComputeWeightedMean(const Pose2List& rMeans, const List<Matrix3>& rCovariances) const
  {
    assert(rMeans.Size() == rCovariances.Size());
    
    // compute sum of inverses and create inverse list
    List<Matrix3> inverses;
    inverses.EnsureCapacity(rCovariances.Size());
    
    Matrix3 sumOfInverses;
    karto_const_forEach(List<Matrix3>, &rCovariances)
    {
      Matrix3 inverse = iter->Inverse();
      inverses.Add(inverse);
      
      sumOfInverses += inverse;
    }
    Matrix3 inverseOfSumOfInverses = sumOfInverses.Inverse();
    
    // compute weighted mean
    Pose2 accumulatedPose;
    kt_double thetaX = 0.0;
    kt_double thetaY = 0.0;
    
    Pose2List::ConstIterator meansIter = rMeans.GetConstIterator();
    karto_const_forEach(List<Matrix3>, &inverses)
    {
      Pose2 pose = *meansIter;
      kt_double angle = pose.GetHeading();
      thetaX += cos(angle);
      thetaY += sin(angle);
      
      Matrix3 weight = inverseOfSumOfInverses * (*iter);
      accumulatedPose += weight * pose;
      
      meansIter++;
    }
    
    thetaX /= rMeans.Size();
    thetaY /= rMeans.Size();
    accumulatedPose.SetHeading(atan2(thetaY, thetaX));
    
    return accumulatedPose;
  }
  
  LocalizedLaserScanList MapperGraph::FindPossibleLoopClosure(LocalizedLaserScan* pScan, const Identifier& rSensorName, kt_int32u& rStartScanIndex)
  {
    // To be a valid loop closure (a chain of candidate loop closure), it must satisfy that
    // (1) all scans in this chain should be closer to current scan than m_pLoopSearchMaximumDistance
    // (2) The length of this candidate chain should be longer than m_pLoopMatchMinimumChainSize
    LocalizedLaserScanList chain; // return value
    
    Pose2 pose = pScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());
    
    const kt_bool isFirstSearchForCurrentTryCloseLoop = (rStartScanIndex == 0);

    // find neighbor scans of pScan, we will not consider these close scans as loop closures
    // BFS starting from current pScan is used to find neighbors
    const LocalizedLaserScanList nearLinkedScans = FindNearLinkedScans(pScan, m_pOpenMapper->m_pLoopSearchMaximumDistance->GetValue());
    if (isFirstSearchForCurrentTryCloseLoop)
    {
      // Reuse the exact near-linked set already computed by the original
      // candidate-generation path; do not perform a second traversal.
      m_pOpenMapper->RecordTryCloseLoopContext(
        pScan, &nearLinkedScans, "PRE_TRY_CLOSE_LOOP");
    }
    
    LocalizedLaserScanList scans = m_pOpenMapper->m_pMapperSensorManager->GetScans(rSensorName);
    kt_size_t nScans = scans.Size();
    for (; rStartScanIndex < nScans; rStartScanIndex++)  // Traversing all scans
    {
      // ---- Phase 2C observation-only: accumulate candidate-generation counters ----
      m_pOpenMapper->m_DiagScansConsidered++;
      
      LocalizedLaserScan* pCandidateScan = scans[rStartScanIndex];
      
      Pose2 candidateScanPose = pCandidateScan->GetReferencePose(m_pOpenMapper->m_pUseScanBarycenter->GetValue());
      // Get distance of the candidate scan to current scan
      kt_double squaredDistance = candidateScanPose.GetPosition().SquaredDistance(pose.GetPosition());
      if (squaredDistance < math::Square(m_pOpenMapper->m_pLoopSearchMaximumDistance->GetValue()) + KT_TOLERANCE) // 10
      {
        // ---- Phase 2C observation-only ----
        m_pOpenMapper->m_DiagScansInDistance++;
        // a linked scan cannot be in the chain
        if (nearLinkedScans.Contains(pCandidateScan) == true)
        {
          // ---- Phase 2C observation-only ----
          m_pOpenMapper->m_DiagScansNearLinked++;
          chain.Clear();
        }
        else
        {
          chain.Add(pCandidateScan);
        }
      }
      else
      {
        // return chain if it is long "enough"
        if (chain.Size() >= m_pOpenMapper->m_pLoopMatchMinimumChainSize->GetValue())
        {
          // ---- Phase 2C observation-only ----
          m_pOpenMapper->m_DiagChainCount++;
          return chain;
        }
        else
        {
          chain.Clear();
        }
      }
    }
    
    // ---- Phase 2C observation-only: the trailing partial chain (possibly below
    //      the minimum chain size) is also a returned candidate chain. ----
    if (!chain.IsEmpty())
    {
      m_pOpenMapper->m_DiagChainCount++;
    }
    return chain;
  }
  
  void MapperGraph::CorrectPoses()
  {
    // optimize scans!
    ScanSolver* pSolver = m_pOpenMapper->m_pScanSolver;
    if (pSolver != NULL)
    {
      pSolver->Compute();
      
      karto_const_forEach(ScanSolver::IdPoseVector, &pSolver->GetCorrections())
      {
        LocalizedObject* pObject = m_pOpenMapper->m_pMapperSensorManager->GetLocalizedObject(iter->GetFirst());
        LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
        
        if (pScan != NULL)
        {
          pScan->SetSensorPose(iter->GetSecond());
        }
        else
        {
          pObject->SetCorrectedPose(iter->GetSecond());
        }
      }
      
      pSolver->Clear();
    }
  }

  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////
  ////////////////////////////////////////////////////////////////////////////////////////

  /**
   * Default constructor
   */
  OpenMapper::OpenMapper(kt_bool multiThreaded)
    : Module("OpenMapper")
    , m_pScanSolver(NULL)
    , m_Initialized(false)
    , m_MultiThreaded(multiThreaded)
    , m_pSequentialScanMatcher(NULL)
    , m_pMapperSensorManager(NULL)
    , m_pGraph(NULL)
    , m_LoopDiagnosticsEnabled(false)
    , m_LoopDiagnosticsPath("")
    , m_LoopDiagnosticsRunId("")
    , m_DiagScansConsidered(0)
    , m_DiagScansInDistance(0)
    , m_DiagScansNearLinked(0)
    , m_DiagChainCount(0)
    , m_EdgeProvenanceEnabled(false)
    , m_EdgeProvenancePath("")
    , m_EdgeProvenanceRunId("")
    , m_EdgeCreationSequence(0)
    , m_PoseGraphDumpPath("")
    , m_PoseGraphDumpDone(-1)
    , m_pEdgeProvenanceMutex(new karto::Mutex())
  {
    // Pre-reserving the buffer keeps the constraint-creation path free of
    // reallocation. The buffer is empty and unused when provenance is off.
    m_EdgeProvenanceBuffer.reserve(4096);
    InitializeParameters();
  }

  /**
   * Default constructor
   */
  OpenMapper::OpenMapper(const char* pName, kt_bool multiThreaded)
    : Module(pName)
    , m_pScanSolver(NULL)
    , m_Initialized(false)
    , m_MultiThreaded(multiThreaded)
    , m_pSequentialScanMatcher(NULL)
    , m_pMapperSensorManager(NULL)
    , m_pGraph(NULL)
    , m_LoopDiagnosticsEnabled(false)
    , m_LoopDiagnosticsPath("")
    , m_LoopDiagnosticsRunId("")
    , m_DiagScansConsidered(0)
    , m_DiagScansInDistance(0)
    , m_DiagScansNearLinked(0)
    , m_DiagChainCount(0)
    , m_EdgeProvenanceEnabled(false)
    , m_EdgeProvenancePath("")
    , m_EdgeProvenanceRunId("")
    , m_EdgeCreationSequence(0)
    , m_PoseGraphDumpPath("")
    , m_PoseGraphDumpDone(-1)
    , m_pEdgeProvenanceMutex(new karto::Mutex())
  {
    // Pre-reserving the buffer keeps the constraint-creation path free of
    // reallocation. The buffer is empty and unused when provenance is off.
    m_EdgeProvenanceBuffer.reserve(4096);
    InitializeParameters();
  }

  /**
   * Destructor
   */
  OpenMapper::~OpenMapper()
  {
    // Graceful-shutdown outputs: the buffered provenance tail and, when
    // configured, a final graph dump so a replay never depends on a request
    // racing with the last scan.
    FlushEdgeProvenance();
    if (m_PoseGraphDumpPath.Size() > 0)
    {
      WritePoseGraphJson(m_PoseGraphDumpPath);
    }

    Reset();

    delete m_pMapperSensorManager;
    delete m_pEdgeProvenanceMutex;
    m_pEdgeProvenanceMutex = NULL;
  }

  void OpenMapper::SetLoopDiagnostics(kt_bool enable, const karto::String& path, const karto::String& runId)
  {
    // Observation-only: only stores configuration; does not alter any SLAM behavior.
    m_LoopDiagnosticsEnabled = enable;
    m_LoopDiagnosticsPath = path;
    m_LoopDiagnosticsRunId = runId;
  }

  void OpenMapper::SetEdgeProvenanceDiagnostics(kt_bool enable,
                                                const karto::String& path,
                                                const karto::String& runId)
  {
    // Observation-only configuration. The disabled path performs no logging,
    // sequence increments, parameter reads, or extra graph traversals.
    m_EdgeProvenanceEnabled = enable;
    m_EdgeProvenancePath = path;
    m_EdgeProvenanceRunId = runId;
    m_EdgeCreationSequence = 0;
    {
      karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
      m_EdgeProvenanceBuffer.clear();
    }
    m_ProbePhaseCache = "UNAVAILABLE";
  }

  void OpenMapper::RefreshProbePhaseCache()
  {
    // One ROS parameter lookup per processed scan instead of one per created
    // constraint: the phase cannot change while a single scan is processed.
    if (!m_EdgeProvenanceEnabled)
    {
      return;
    }
    std::string phase("UNAVAILABLE");
    ros::param::getCached("/constraint_realizability_pilot/probe_phase", phase);
    m_ProbePhaseCache = phase;
  }

  kt_bool OpenMapper::HasPendingEdgeProvenance()
  {
    karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
    return m_EdgeProvenanceBuffer.empty() ? false : true;
  }

  namespace
  {
    void CopyProvenanceText(char* pTarget, kt_int32u length, const std::string& rValue)
    {
      if (length == 0)
      {
        return;
      }
      std::snprintf(pTarget, length, "%s", rValue.c_str());
      pTarget[length - 1] = '\0';
    }
  }

  void OpenMapper::MaybeWritePoseGraphDump()
  {
    // Called from the mapper's own processing thread, at the end of a scan.
    // Reading the graph from a foreign thread can block against the mapper's
    // own graph work, which is why the dump is never written from the
    // maintenance thread.
    if (m_PoseGraphDumpPath.Size() == 0)
    {
      return;
    }
    int request = 0;
    ros::param::getCached(ros::this_node::getName() + "/pose_graph_dump_request",
                          request);
    if (request == m_PoseGraphDumpDone)
    {
      return;
    }
    if (WritePoseGraphJson(m_PoseGraphDumpPath))
    {
      m_PoseGraphDumpDone = request;
    }
  }

  void OpenMapper::SetPoseGraphDumpPath(const karto::String& rPath)
  {
    m_PoseGraphDumpPath = rPath;
    m_PoseGraphDumpDone = -1;   // force a dump on the first request
  }

  kt_bool OpenMapper::WritePoseGraphJson(const karto::String& rPath)
  {
    // Observation-only, arm-independent graph dump used by the same-input
    // replay comparison.  It reads the graph and writes a file; it never
    // changes the graph, the solver or any matcher decision.
    if (rPath.Size() == 0 || m_pGraph == NULL || m_pGraph->GetVertices().Size() == 0)
    {
      return false;
    }
    std::ofstream out(rPath.ToCString(), std::ios::trunc);
    if (!out.is_open())
    {
      return false;
    }

    const MapperGraph::VertexList& vertices = m_pGraph->GetVertices();
    out << "{\"dump_version\":1,\"run_id\":\""
        << m_EdgeProvenanceRunId.ToCString() << "\"";
    out << ",\"nodes\":[";
    for (kt_int32s i = 0; i < vertices.Size(); i++)
    {
      Vertex<LocalizedObjectPtr>* pVertex = vertices[i];
      LocalizedObject* pObject = pVertex->GetVertexObject();
      Pose2 pose = pObject->GetCorrectedPose();
      if (i > 0) out << ",";
      out << "{\"index\":" << i
          << ",\"state_id\":" << pObject->GetStateId()
          << ",\"unique_id\":" << pObject->GetUniqueId()
          << ",\"x\":" << LoopDiagDouble(pose.GetX())
          << ",\"y\":" << LoopDiagDouble(pose.GetY())
          << ",\"theta\":" << LoopDiagDouble(pose.GetHeading()) << "}";
    }
    out << "]";

    const MapperGraph::EdgeList& edges = m_pGraph->GetEdges();
    out << ",\"edges\":[";
    for (kt_int32s i = 0; i < edges.Size(); i++)
    {
      Edge<LocalizedObjectPtr>* pEdge = edges[i];
      LocalizedObject* pSource = pEdge->GetSource()->GetVertexObject();
      LocalizedObject* pTarget = pEdge->GetTarget()->GetVertexObject();
      LinkInfo* pLinkInfo = static_cast<LinkInfo*>(pEdge->GetLabel());
      if (i > 0) out << ",";
      out << "{\"index\":" << i
          << ",\"source_state_id\":" << pSource->GetStateId()
          << ",\"target_state_id\":" << pTarget->GetStateId()
          << ",\"source_unique_id\":" << pSource->GetUniqueId()
          << ",\"target_unique_id\":" << pTarget->GetUniqueId();
      if (pLinkInfo != NULL)
      {
        Pose2 mean = pLinkInfo->GetPoseDifference();
        Matrix3 covariance = pLinkInfo->GetCovariance();
        out << ",\"measurement\":{\"dx\":" << LoopDiagDouble(mean.GetX())
            << ",\"dy\":" << LoopDiagDouble(mean.GetY())
            << ",\"dtheta\":" << LoopDiagDouble(mean.GetHeading()) << "}"
            << ",\"covariance_3x3\":[["
            << LoopDiagDouble(covariance(0, 0)) << "," << LoopDiagDouble(covariance(0, 1))
            << "," << LoopDiagDouble(covariance(0, 2)) << "],["
            << LoopDiagDouble(covariance(1, 0)) << "," << LoopDiagDouble(covariance(1, 1))
            << "," << LoopDiagDouble(covariance(1, 2)) << "],["
            << LoopDiagDouble(covariance(2, 0)) << "," << LoopDiagDouble(covariance(2, 1))
            << "," << LoopDiagDouble(covariance(2, 2)) << "]]";
      }
      out << "}";
    }
    out << "]}";
    out.close();
    return true;
  }

  void OpenMapper::FlushEdgeProvenance(const karto::String& rPath)
  {
    std::vector<EdgeProvenanceEntry> pending;
    {
      karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
      if (m_EdgeProvenanceBuffer.empty())
      {
        return;
      }
      pending.swap(m_EdgeProvenanceBuffer);
    }

    std::string path = rPath.Size() > 0 ? std::string(rPath.ToCString())
                                        : std::string(m_EdgeProvenancePath.ToCString());
    if (m_EdgeProvenancePath.Size() == 0 && rPath.Size() == 0)
    {
      // Nothing was configured: the records are dropped deliberately rather
      // than written into an unknown location.
      return;
    }

    std::ofstream out(path.c_str(), std::ios::app);
    if (!out.is_open())
    {
      // Put the records back so a later flush can still write them.
      karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
      pending.insert(pending.end(), m_EdgeProvenanceBuffer.begin(),
                     m_EdgeProvenanceBuffer.end());
      m_EdgeProvenanceBuffer.swap(pending);
      return;
    }

    for (size_t index = 0; index < pending.size(); index++)
    {
      const EdgeProvenanceEntry& entry = pending[index];
      std::ostringstream oss;
      if (entry.recordType == 0)
      {
        const EdgeProvenanceRecord& r = entry.constraint;
        oss << "{\"record_type\":\"constraint_created\""
            << ",\"schema_version\":1"
            << ",\"run_id\":\"" << m_EdgeProvenanceRunId.ToCString() << "\""
            << ",\"creation_sequence\":" << r.creationSequence
            << ",\"canonical_edge_identity\":[" << r.sourceStateId
            << "," << r.targetStateId << "]"
            << ",\"source_state_id\":" << r.sourceStateId
            << ",\"target_state_id\":" << r.targetStateId
            << ",\"source_unique_id\":" << r.sourceUniqueId
            << ",\"target_unique_id\":" << r.targetUniqueId
            << ",\"source_pose\":{\"x\":" << LoopDiagDouble(r.sourcePose[0])
            << ",\"y\":" << LoopDiagDouble(r.sourcePose[1])
            << ",\"yaw\":" << LoopDiagDouble(r.sourcePose[2]) << "}"
            << ",\"target_pose\":{\"x\":" << LoopDiagDouble(r.targetPose[0])
            << ",\"y\":" << LoopDiagDouble(r.targetPose[1])
            << ",\"yaw\":" << LoopDiagDouble(r.targetPose[2]) << "}"
            << ",\"creation_provenance\":\""
            << ConstraintProvenanceName(static_cast<ConstraintCreationProvenance>(
                 r.provenance)) << "\""
            << ",\"creation_function\":\"" << r.creationFunction << "\""
            << ",\"creation_stage\":\"" << r.creationStage << "\""
            << ",\"current_keyscan_state_id\":" << r.currentKeyscanStateId
            << ",\"current_keyscan_unique_id\":" << r.currentKeyscanUniqueId
            << ",\"relative_mean\":{\"x\":" << LoopDiagDouble(r.relativeMean[0])
            << ",\"y\":" << LoopDiagDouble(r.relativeMean[1])
            << ",\"yaw\":" << LoopDiagDouble(r.relativeMean[2]) << "}"
            << ",\"covariance_3x3\":[["
            << LoopDiagDouble(r.covariance[0][0]) << "," << LoopDiagDouble(r.covariance[0][1])
            << "," << LoopDiagDouble(r.covariance[0][2]) << "],["
            << LoopDiagDouble(r.covariance[1][0]) << "," << LoopDiagDouble(r.covariance[1][1])
            << "," << LoopDiagDouble(r.covariance[1][2]) << "],["
            << LoopDiagDouble(r.covariance[2][0]) << "," << LoopDiagDouble(r.covariance[2][1])
            << "," << LoopDiagDouble(r.covariance[2][2]) << "]]"
            << ",\"matcher_type\":\"" << r.matcherType << "\""
            << ",\"match_response\":"
            << OptionalDiagDouble(r.hasMatchResponse, r.matchResponse)
            << ",\"match_threshold\":"
            << OptionalDiagDouble(r.hasMatchThreshold, r.matchThreshold)
            << ",\"coarse_response\":"
            << OptionalDiagDouble(r.hasCoarseResponse, r.coarseResponse)
            << ",\"coarse_threshold\":"
            << OptionalDiagDouble(r.hasCoarseThreshold, r.coarseThreshold)
            << ",\"solver_add_constraint_called\":"
            << LoopDiagBool(r.solverAddConstraintCalled)
            << ",\"graph_edge_count_after_creation\":"
            << r.graphEdgeCountAfterCreation
            << ",\"wall_time\":" << LoopDiagDouble(r.wallTime)
            << ",\"sim_time\":" << LoopDiagDouble(r.simTime)
            << ",\"before_or_during_probe\":\"" << r.probePhase << "\"}"
            ;
      }
      else
      {
        const TryCloseLoopContextRecord& r = entry.context;
        oss << "{\"record_type\":\"try_close_loop_context\""
            << ",\"schema_version\":1"
            << ",\"run_id\":\"" << m_EdgeProvenanceRunId.ToCString() << "\""
            << ",\"stage\":\"" << r.stage << "\""
            << ",\"current_keyscan_state_id\":" << r.currentKeyscanStateId
            << ",\"current_keyscan_unique_id\":" << r.currentKeyscanUniqueId
            << ",\"graph_edges\":[";
        for (size_t e = 0; e < r.graphEdges.size(); e++)
        {
          if (e > 0) oss << ",";
          oss << "[" << r.graphEdges[e].first << "," << r.graphEdges[e].second << "]";
        }
        oss << "]";
        if (r.hasNearLinkedScans)
        {
          oss << ",\"near_linked_scan_ids\":[";
          for (size_t s = 0; s < r.nearLinkedScanIds.size(); s++)
          {
            if (s > 0) oss << ",";
            oss << r.nearLinkedScanIds[s];
          }
          oss << "]";
        }
        else
        {
          oss << ",\"near_linked_scan_ids\":null";
        }
        oss << ",\"wall_time\":" << LoopDiagDouble(r.wallTime)
            << ",\"sim_time\":" << LoopDiagDouble(r.simTime)
            << "}";
      }
      out << oss.str() << "\n";
    }
    out.close();
  }

  void OpenMapper::ResetLoopDiagnostics()
  {
    m_DiagScansConsidered = 0;
    m_DiagScansInDistance = 0;
    m_DiagScansNearLinked = 0;
    m_DiagChainCount = 0;
  }

  void OpenMapper::AppendLoopDiagnosticsLine(const std::string& rLine)
  {
    if (!m_LoopDiagnosticsEnabled)
    {
      return;
    }
    if (m_LoopDiagnosticsPath.Size() == 0)
    {
      return;
    }
    std::ofstream out(m_LoopDiagnosticsPath.ToCString(), std::ios::app);
    if (out.is_open())
    {
      out << rLine << "\n";
      out.close();
    }
  }

  void OpenMapper::RecordNewConstraint(
    Edge<LocalizedObjectPtr>* pEdge,
    LocalizedObject* pFromObject,
    LocalizedObject* pToObject,
    const ConstraintCreationContext& rContext,
    kt_bool solverAddConstraintCalled)
  {
    if (!m_EdgeProvenanceEnabled)
    {
      return;
    }

    LinkInfo* pLinkInfo = static_cast<LinkInfo*>(pEdge->GetLabel());
    if (pLinkInfo == NULL)
    {
      return;
    }
    const Pose2 relativeMean = pLinkInfo->GetPoseDifference();
    const Matrix3 covariance = pLinkInfo->GetCovariance();
    const Pose2 sourcePose = pFromObject->GetCorrectedPose();
    const Pose2 targetPose = pToObject->GetCorrectedPose();
    LocalizedLaserScan* pCurrentScan = dynamic_cast<LocalizedLaserScan*>(pToObject);

    // Critical path: copy plain values into one pre-sized struct and append it.
    // No formatting, no allocation, no parameter lookup, no file I/O.
    EdgeProvenanceEntry entry;
    entry.recordType = 0;
    EdgeProvenanceRecord& r = entry.constraint;
    m_EdgeCreationSequence++;
    r.creationSequence = static_cast<kt_int64s>(m_EdgeCreationSequence);
    r.sourceStateId = pFromObject->GetStateId();
    r.targetStateId = pToObject->GetStateId();
    r.sourceUniqueId = pFromObject->GetUniqueId();
    r.targetUniqueId = pToObject->GetUniqueId();
    r.currentKeyscanStateId = (pCurrentScan != NULL)
        ? static_cast<kt_int64s>(pCurrentScan->GetStateId()) : -1;
    r.currentKeyscanUniqueId = (pCurrentScan != NULL)
        ? static_cast<kt_int64s>(pCurrentScan->GetUniqueId()) : -1;
    r.provenance = static_cast<kt_int32u>(rContext.provenance);
    r.solverAddConstraintCalled = solverAddConstraintCalled;
    r.hasMatchResponse = rContext.hasMatchResponse;
    r.hasMatchThreshold = rContext.hasMatchThreshold;
    r.hasCoarseResponse = rContext.hasCoarseResponse;
    r.hasCoarseThreshold = rContext.hasCoarseThreshold;
    r.matchResponse = rContext.matchResponse;
    r.matchThreshold = rContext.matchThreshold;
    r.coarseResponse = rContext.coarseResponse;
    r.coarseThreshold = rContext.coarseThreshold;
    r.sourcePose[0] = sourcePose.GetX();
    r.sourcePose[1] = sourcePose.GetY();
    r.sourcePose[2] = sourcePose.GetHeading();
    r.targetPose[0] = targetPose.GetX();
    r.targetPose[1] = targetPose.GetY();
    r.targetPose[2] = targetPose.GetHeading();
    r.relativeMean[0] = relativeMean.GetX();
    r.relativeMean[1] = relativeMean.GetY();
    r.relativeMean[2] = relativeMean.GetHeading();
    for (kt_int32u row = 0; row < 3; row++)
    {
      for (kt_int32u col = 0; col < 3; col++)
      {
        r.covariance[row][col] = covariance(row, col);
      }
    }
    r.graphEdgeCountAfterCreation =
        (m_pGraph != NULL ? static_cast<kt_int64s>(m_pGraph->GetEdges().Size()) : 0);
    r.wallTime = ros::WallTime::now().toSec();
    r.simTime = ros::Time::now().toSec();
    CopyProvenanceText(r.creationFunction, kProvenanceTextLen, rContext.creationFunction);
    CopyProvenanceText(r.creationStage, kProvenanceTextLen, rContext.creationStage);
    CopyProvenanceText(r.matcherType, kProvenanceTextLen, rContext.matcherType);
    CopyProvenanceText(r.probePhase, kProvenanceTextLen, m_ProbePhaseCache);

    karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
    m_EdgeProvenanceBuffer.push_back(entry);
  }

  void OpenMapper::RecordTryCloseLoopContext(
    LocalizedLaserScan* pScan,
    const LocalizedLaserScanList* pNearLinkedScans,
    const char* stage)
  {
    if (!m_EdgeProvenanceEnabled)
    {
      return;
    }

    EdgeProvenanceEntry entry;
    entry.recordType = 1;
    TryCloseLoopContextRecord& r = entry.context;
    r.currentKeyscanStateId = pScan->GetStateId();
    r.currentKeyscanUniqueId = pScan->GetUniqueId();
    r.hasNearLinkedScans = (pNearLinkedScans != NULL) ? true : false;
    r.wallTime = ros::WallTime::now().toSec();
    r.simTime = ros::Time::now().toSec();
    CopyProvenanceText(r.stage, kProvenanceTextLen,
                       std::string(stage != NULL ? stage : "UNKNOWN"));

    // Copy the graph edge endpoints and the near-linked scan ids as plain
    // integers; the JSON text is produced later by the flush path.
    if (m_pGraph != NULL)
    {
      const MapperGraph::EdgeList& edges = m_pGraph->GetEdges();
      r.graphEdges.reserve(edges.Size());
      karto_const_forEach(MapperGraph::EdgeList, &edges)
      {
        r.graphEdges.push_back(std::make_pair(
            static_cast<kt_int64s>((*iter)->GetSource()->GetVertexObject()->GetStateId()),
            static_cast<kt_int64s>((*iter)->GetTarget()->GetVertexObject()->GetStateId())));
      }
    }
    if (pNearLinkedScans != NULL)
    {
      r.nearLinkedScanIds.reserve(pNearLinkedScans->Size());
      karto_const_forEach(LocalizedLaserScanList, pNearLinkedScans)
      {
        r.nearLinkedScanIds.push_back(static_cast<kt_int64s>((*iter)->GetStateId()));
      }
    }

    karto::Mutex::ScopedLock lock(*m_pEdgeProvenanceMutex);
    m_EdgeProvenanceBuffer.push_back(entry);
  }

  std::string OpenMapper::BuildLoopDiagBaseFragment(LocalizedLaserScan* pScan)
  {
    std::ostringstream oss;
    Pose2 refPose = pScan->GetReferencePose(m_pUseScanBarycenter->GetValue());
    kt_int64s nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
    oss << "\"wall_time_ms\":" << nowMs
        << ",\"run_id\":\"" << m_LoopDiagnosticsRunId.ToCString() << "\""
        << ",\"scan_id\":" << pScan->GetStateId()
        << ",\"scan_unique_id\":" << pScan->GetUniqueId()
        << ",\"scan_pose_x\":" << LoopDiagDouble(refPose.GetX())
        << ",\"scan_pose_y\":" << LoopDiagDouble(refPose.GetY())
        << ",\"scan_yaw\":" << LoopDiagDouble(refPose.GetHeading())
        << ",\"loop_search_triggered\":true"
        << ",\"historical_scans_considered\":" << m_DiagScansConsidered
        << ",\"historical_scans_in_distance\":" << m_DiagScansInDistance
        << ",\"historical_scans_filtered_near_linked\":" << m_DiagScansNearLinked
        << ",\"candidate_chain_count\":" << m_DiagChainCount;
    return oss.str();
  }

  void OpenMapper::InitializeParameters()
  {
    m_pUseScanMatching = new Parameter<kt_bool>(GetParameterSet(), "UseScanMatching", "Mapper::Use::Scan Matching", "UseScanMatching", true);
    m_pUseScanBarycenter = new Parameter<kt_bool>(GetParameterSet(), "UseScanBarycenter", "Mapper::Use::Scan Barycenter", "UseScanBarycenter", true);
    m_pMinimumTravelDistance = new Parameter<kt_double>(GetParameterSet(), "MinimumTravelDistance", "Mapper::Minimum Travel::Distance", "MinimumTravelDistance", 0.2);
    m_pMinimumTravelHeading = new Parameter<kt_double>(GetParameterSet(), "MinimumTravelHeading", "Mapper::Minimum Travel::Heading", "MinimumTravelHeading", math::DegreesToRadians(20));

    m_pScanBufferSize = new Parameter<kt_int32u>(GetParameterSet(), "ScanBufferSize", "Mapper::Scan Buffer::Size", "ScanBufferSize", 70);
    m_pScanBufferMaximumScanDistance = new Parameter<kt_double>(GetParameterSet(), "ScanBufferMaximumScanDistance", "Mapper::Scan Buffer::Maximum Scan Distance", "ScanBufferMaximumScanDistance", 20);
    m_pUseResponseExpansion = new Parameter<kt_bool>(GetParameterSet(), "UseResponseExpansion", "Mapper::Use::Response Expansion", "UseResponseExpansion", false);

    m_pDistanceVariancePenalty = new Parameter<kt_double>(GetParameterSet(), "DistanceVariancePenalty", "Mapper::Scan Matcher::Distance Variance Penalty", "DistanceVariancePenalty",  math::Square(0.3));
    m_pMinimumDistancePenalty = new Parameter<kt_double>(GetParameterSet(), "MinimumDistancePenalty", "Mapper::Scan Matcher::Minimum Distance Penalty", "MinimumDistancePenalty", 0.5);
    m_pAngleVariancePenalty = new Parameter<kt_double>(GetParameterSet(), "AngleVariancePenalty", "Mapper::Scan Matcher::Angle Variance Penalty", "AngleVariancePenalty", math::Square(math::DegreesToRadians(20)));
    m_pMinimumAnglePenalty = new Parameter<kt_double>(GetParameterSet(), "MinimumAnglePenalty", "Mapper::Scan Matcher::Minimum Angle Penalty", "MinimumAnglePenalty", 0.9);
    
    m_pLinkMatchMinimumResponseFine = new Parameter<kt_double>(GetParameterSet(), "LinkMatchMinimumResponseFine", "Mapper::Link::Match Minimum Response Fine", "LinkMatchMinimumResponseFine", 0.6);
    m_pLinkScanMaximumDistance = new Parameter<kt_double>(GetParameterSet(), "LinkScanMaximumDistance", "Mapper::Link::Scan Maximum Distance", "LinkScanMaximumDistance", 10.0);

    m_pCorrelationSearchSpaceDimension = new Parameter<kt_double>(GetParameterSet(), "CorrelationSearchSpaceDimension", "Mapper::Correlation Search Space::Dimension", "CorrelationSearchSpaceDimension", 0.3);
    m_pCorrelationSearchSpaceResolution = new Parameter<kt_double>(GetParameterSet(), "CorrelationSearchSpaceResolution", "Mapper::Correlation Search Space::Resolution", "CorrelationSearchSpaceResolution", 0.01);
    m_pCorrelationSearchSpaceSmearDeviation = new Parameter<kt_double>(GetParameterSet(), "CorrelationSearchSpaceSmearDeviation", "Mapper::Correlation Search Space::Smear Deviation", "CorrelationSearchSpaceSmearDeviation", 0.03);
    m_pCoarseSearchAngleOffset = new Parameter<kt_double>(GetParameterSet(), "CoarseSearchAngleOffset", "Mapper::Scan Matcher::Coarse Search Angle Offset", "CoarseSearchAngleOffset", math::DegreesToRadians(20));
    m_pFineSearchAngleOffset = new Parameter<kt_double>(GetParameterSet(), "FineSearchAngleOffset", "Mapper::Scan Matcher::Fine Search Angle Offset", "FineSearchAngleOffset", math::DegreesToRadians(0.2));
    m_pCoarseAngleResolution = new Parameter<kt_double>(GetParameterSet(), "CoarseAngleResolution", "Mapper::Scan Matcher::Coarse Angle Resolution", "CoarseAngleResolution", math::DegreesToRadians(2));
    
    m_pLoopSearchSpaceDimension = new Parameter<kt_double>(GetParameterSet(), "LoopSearchSpaceDimension", "Mapper::Loop Correlation Search Space::Dimension", "LoopSearchSpaceDimension", 8.0);
    m_pLoopSearchSpaceResolution = new Parameter<kt_double>(GetParameterSet(), "LoopSearchSpaceResolution", "Mapper::Loop Correlation Search Space::Resolution", "LoopSearchSpaceResolution", 0.05);
    m_pLoopSearchSpaceSmearDeviation = new Parameter<kt_double>(GetParameterSet(), "LoopSearchSpaceSmearDeviation", "Mapper::Loop Correlation Search Space::Smear Deviation", "LoopSearchSpaceSmearDeviation", 0.03);

    m_pLoopSearchMaximumDistance = new Parameter<kt_double>(GetParameterSet(), "LoopSearchMaximumDistance", "Mapper::Loop::Search Maximum Distance", "LoopSearchMaximumDistance", 10.0);
    m_pLoopMatchMinimumChainSize = new Parameter<kt_int32u>(GetParameterSet(), "LoopMatchMinimumChainSize", "Mapper::Loop::Match::Minimum Chain Size", "LoopMatchMinimumChainSize", 4);
    m_pLoopMatchMaximumVarianceCoarse = new Parameter<kt_double>(GetParameterSet(), "LoopMatchMaximumVarianceCoarse", "Mapper::Loop::Match::Maximum Variance Coarse", "LoopMatchMaximumVarianceCoarse", math::Square(0.4));
    m_pLoopMatchMinimumResponseCoarse = new Parameter<kt_double>(GetParameterSet(), "LoopMatchMinimumResponseCoarse", "Mapper::Loop::Match::Minimum Response Coarse", "LoopMatchMinimumResponseCoarse", 0.7);
    m_pLoopMatchMinimumResponseFine = new Parameter<kt_double>(GetParameterSet(), "LoopMatchMinimumResponseFine", "Mapper::Loop::Match::Minimum Response Fine", "LoopMatchMinimumResponseFine", 0.7);  // 这是一个归一化值，取值范围在0-1之间，表示点云与地图的命中比例
    std::cout << m_pLoopMatchMinimumResponseCoarse << std::endl;
  }

  void OpenMapper::Initialize(kt_double rangeThreshold)
  {
    if (m_Initialized == false)
    {
      // create sequential scan and loop matcher
      m_pSequentialScanMatcher = ScanMatcher::Create(this, m_pCorrelationSearchSpaceDimension->GetValue(), m_pCorrelationSearchSpaceResolution->GetValue(), m_pCorrelationSearchSpaceSmearDeviation->GetValue(), rangeThreshold);
      assert(m_pSequentialScanMatcher);

      m_pMapperSensorManager = new MapperSensorManager(m_pScanBufferSize->GetValue(), m_pScanBufferMaximumScanDistance->GetValue());

      m_pGraph = new MapperGraph(this, rangeThreshold);

      m_Initialized = true;
    }
    else
    {
      Log(LOG_WARNING, "Mapper already initialized");
    }
  }

  void OpenMapper::Reset()
  {
    Module::Reset();

    delete m_pSequentialScanMatcher;
    m_pSequentialScanMatcher = NULL;

    delete m_pGraph;
    m_pGraph = NULL;

    delete m_pMapperSensorManager;
    m_pMapperSensorManager = NULL;

    m_Initialized = false;
  }

  kt_bool OpenMapper::Process(Object* pObject)
  {
    // ROS_DEBUG("Test: Process new scan!!!");
    if (pObject == NULL)
    {
      return false;
    }
    
    kt_bool isObjectProcessed = Module::Process(pObject);

    if (IsLaserRangeFinder(pObject))
    {
      LaserRangeFinder* pLaserRangeFinder = dynamic_cast<LaserRangeFinder*>(pObject);
 
      if (m_Initialized == false)
      {
        // initialize mapper with range threshold from sensor
        Initialize(pLaserRangeFinder->GetRangeThreshold());
      }
      
      // register sensor
      m_pMapperSensorManager->RegisterSensor(pLaserRangeFinder->GetIdentifier());
      
      return true;
    }
    
    LocalizedObject* pLocalizedObject = dynamic_cast<LocalizedObject*>(pObject);
    if (pLocalizedObject != NULL)
    {
      LocalizedLaserScan* pScan = dynamic_cast<LocalizedLaserScan*>(pObject);
      if (pScan != NULL)
      {
        karto::LaserRangeFinder* pLaserRangeFinder = pScan->GetLaserRangeFinder();
        
        // validate scan
        if (pLaserRangeFinder == NULL)
        {
          return false;
        }
        
        // validate scan. Throws exception if scan is invalid.
        pLaserRangeFinder->Validate(pScan);
        
        if (m_Initialized == false)
        {
          // initialize mapper with range threshold from sensor
          Initialize(pLaserRangeFinder->GetRangeThreshold());
        }
      }

      // ensures sensor has been registered with mapper--does nothing if the sensor has already been registered
      m_pMapperSensorManager->RegisterSensor(pLocalizedObject->GetSensorIdentifier());

      // Observation-only: refresh the cached probe phase once per scan so the
      // per-constraint path performs no ROS parameter lookup at all.
      RefreshProbePhaseCache();

      // get last scan
      LocalizedLaserScan* pLastScan = m_pMapperSensorManager->GetLastScan(pLocalizedObject->GetSensorIdentifier());
      
      // update scans corrected pose based on last correction
      if (pLastScan != NULL)
      {
        Transform lastTransform(pLastScan->GetOdometricPose(), pLastScan->GetCorrectedPose());
        pLocalizedObject->SetCorrectedPose(lastTransform.TransformPose(pLocalizedObject->GetOdometricPose()));
      }
      
      // check custom data if object is not a scan or if scan has not moved enough (i.e.,
      // scan is outside minimum boundary or if heading is larger then minimum heading)
      if (pScan == NULL || (!HasMovedEnough(pScan, pLastScan) && !pScan->IsGpsReadingValid()))
      {
        if (pLocalizedObject->HasCustomItem() == true)
        {
          m_pMapperSensorManager->AddLocalizedObject(pLocalizedObject);
          
          // add to graph
          m_pGraph->AddVertex(pLocalizedObject);
          m_pGraph->AddEdges(pLocalizedObject);
          
          return true;
        }
        
        return false;
      }
      
      /////////////////////////////////////////////
      // object is a key scan
      
      Matrix3 covariance;
      covariance.SetToIdentity();
      kt_bool hasSequentialMatchResponse = false;
      kt_double sequentialMatchResponse = 0.0;
      
      // correct scan (if not first scan)
      if (m_pUseScanMatching->GetValue() && pLastScan != NULL)
      {
        Pose2 bestPose;
        // Get running scan will register this scan to the local map (formed by running scans)
        sequentialMatchResponse = m_pSequentialScanMatcher->MatchScan(
          pScan,
          m_pMapperSensorManager->GetRunningScans(pScan->GetSensorIdentifier()),
          bestPose, covariance);
        hasSequentialMatchResponse = true;
        pScan->SetSensorPose(bestPose);
      }
      
      ScanMatched(pScan);
      
      // add scan to buffer and assign id
      m_pMapperSensorManager->AddLocalizedObject(pLocalizedObject);
      
      if (m_pUseScanMatching->GetValue())
      {
        // add to graph
        m_pGraph->AddVertex(pScan);
        m_pGraph->AddEdges(pScan, covariance, hasSequentialMatchResponse,
                           sequentialMatchResponse);  // AddEdges tries the ordinary graph-link paths before explicit loop search.
        
        m_pMapperSensorManager->AddRunningScan(pScan); // Add current scan to running scan. Before this, RunningScan has been used to add edges for pScan
        
        List<Identifier> sensorNames = m_pMapperSensorManager->GetSensorNames();

        kt_bool pgHasOptimized = false;
        karto_const_forEach(List<Identifier>, &sensorNames)
        {
          // ROS_WARN("Test: Try loop closure...");
          pgHasOptimized = m_pGraph->TryCloseLoop(pScan, *iter);
        }   
        if(!pgHasOptimized){
          m_pGraph->CorrectPoses();  // For PG optimization
        } 
      }
      
      m_pMapperSensorManager->SetLastScan(pScan);
      
      ScanMatchingEnd(pScan);
      
      isObjectProcessed = true;
    } // if object is LocalizedObject
    
    MaybeWritePoseGraphDump();
    return isObjectProcessed;
  }

  kt_bool OpenMapper::HasMovedEnough(LocalizedLaserScan* pScan, LocalizedLaserScan* pLastScan) const
  {
    // test if first scan
    if (pLastScan == NULL)
    {
      return true;
    }
    
    Pose2 lastScannerPose = pLastScan->GetSensorAt(pLastScan->GetOdometricPose());
    Pose2 scannerPose = pScan->GetSensorAt(pScan->GetOdometricPose());

    // test if we have turned enough
    kt_double deltaHeading = math::NormalizeAngle(scannerPose.GetHeading() - lastScannerPose.GetHeading());
    if (fabs(deltaHeading) >= m_pMinimumTravelHeading->GetValue())
    {
      return true;
    }

    // test if we have moved enough
    kt_double squaredTravelDistance = lastScannerPose.GetPosition().SquaredDistance(scannerPose.GetPosition());
    if (squaredTravelDistance >= math::Square(m_pMinimumTravelDistance->GetValue()) - KT_TOLERANCE)
    {
      return true;
    }

    return false;
  }

  const LocalizedLaserScanList OpenMapper::GetAllProcessedScans() const
  {
    LocalizedLaserScanList allScans;

    if (m_pMapperSensorManager != NULL)
    {
      allScans = m_pMapperSensorManager->GetAllScans();
    }

    return allScans;
  }

  const LocalizedObjectList OpenMapper::GetAllProcessedObjects() const
  {
    LocalizedObjectList allObjects;

    if (m_pMapperSensorManager != NULL)
    {
      // BUGBUG: inefficient?  should return right away?
      allObjects = m_pMapperSensorManager->GetAllObjects();
    }

    return allObjects;
  }

  ScanSolver* OpenMapper::GetScanSolver() const
  {
    return m_pScanSolver;
  }

  void OpenMapper::SetScanSolver(ScanSolver* pScanOptimizer)
  {
    m_pScanSolver = pScanOptimizer;
  }

  MapperGraph* OpenMapper::GetGraph() const
  {
    return m_pGraph;
  }

  ScanMatcher* OpenMapper::GetSequentialScanMatcher() const
  {
    return m_pSequentialScanMatcher;
  }

  ScanMatcher* OpenMapper::GetLoopScanMatcher() const
  {
    return m_pGraph->GetLoopScanMatcher();
  }  

}
