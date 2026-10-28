import axiosClient from './axiosClient';

export const projectService = {
  // Fetch Planned Service data by Project ID
  getProjectServicePlanned: async (projectId) => {
    return await axiosClient.get('/GetProjectServicePlanned', {
      params: { ProjectId: projectId },
    });
  },

  // Fetch Planned vs Actual Service data by Project ID
  getProjectServiceActual: async (projectId) => {
    return await axiosClient.get('/GetProjectServiceActual', {
      params: { ProjectId: projectId },
    });
  },
};
