import * as React from "react";
import Box from "@mui/material/Box";
import {DataGrid} from "@mui/x-data-grid";

export default function Datatable({ columns, rows, height }) {
    
    return (
        <Box sx={{ height: height,width: "100%"}}>
            <DataGrid
                rows={rows}
                columns={columns}
                columnHeaderHeight={35}
                rowHeight={35}
                pageSizeOptions={[10, 50, 100]}
                initialState={{
                    pagination: {
                        paginationModel: { pageSize: 10 }
                    }
                }}
                showToolbar
                disableRowSelectionOnClick
                sx={{
                    "& .MuiDataGrid-columnHeaders": {
                        position: "sticky",
                        top: 0,
                        backgroundColor: "#084b6f",
                        zIndex: 1,
                    },
                    "& .MuiDataGrid-columnHeaderTitleContainer": {
                        overflow: "visible",
                    },
                    "& .MuiDataGrid-menuIcon": {
                        visibility: "visible",
                        width: "auto",
                    },
                    "& .MuiDataGrid-columnHeaderTitle":{
                        fontWeight:"bold",
                        color:"white"
                    },
                    "& .MuiDataGrid-columnHeader":{
                        background:"#084b6f85",
                        color:"white",
                        fontSize:"14px"
                    },
                    "& .MuiDataGrid-columnHeader .MuiIconButton-root": {
                        backgroundColor: "transparent !important",
                        padding: "4px",
                    },

                    // REMOVE HOVER BACKGROUND
                    "& .MuiDataGrid-columnHeader .MuiIconButton-root:hover": {
                        backgroundColor: "transparent",
                    },

                    // CHANGE SORT SVG COLOR
                    "& .MuiDataGrid-sortIcon": {
                        color: "white",
                        opacity: 1,     // make it always visible
                    },

                    // INACTIVE SORT ICON COLOR
                    "& .MuiDataGrid-columnHeader:not(.MuiDataGrid-columnHeader--sorted) .MuiDataGrid-sortIcon":
                    {
                        color: "white",
                        opacity: 1,
                    },
                    "& .MuiDataGrid-columnHeaders .MuiSvgIcon-root": {
                        color: "white"
                    },
                    // ACTIVE SORT ICON COLOR
                    "& .MuiDataGrid-columnHeader--sorted .MuiDataGrid-sortIcon": {
                        color: "#00e5ff",
                    },

                    // (OPTIONAL) Remove ripple effect
                    "& .MuiIconButton-root": {
                    "& .MuiTouchRipple-root": {
                            display: "none",
                        },
                    },

                    "& .MuiDataGrid-toolbarContainer": {
                        backgroundColor: "#084b6f",
                    },
                    "& .MuiDataGrid-cell":{
                        fontSize:"14px"
                    },
                }}
            />
        </Box>
    );
}